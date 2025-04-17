import sys
import os
import shutil
from clang.cindex import Config, Index, Cursor, CursorKind, AccessSpecifier, StorageClass, TranslationUnit
from types import SimpleNamespace
from enum import Enum

# see: https://emscripten.org/docs/porting/connecting_cpp_and_javascript/embind.html#object-ownership
class FunctionReturnValuePolicy(Enum):
    DEFAULT = 0
    TAKE_OWNERSHIP = 1
    REFERENCE = 2

# see:  https://emscripten.org/docs/porting/connecting_cpp_and_javascript/embind.html#memory-management
class ClassObjectMemoryManagement(Enum):
    HANDY = 0
    SMART_PTR = 1

class BindingStructure(Enum):
    FLATTENED = 0
    STRUCTURAL = 1


######## Project default configurations ################
class ProjectConfig:
    def __init__(self):
        self.FuncReturnValuePolicy = FunctionReturnValuePolicy.REFERENCE
        self.ClassObjectMemoryManagement = ClassObjectMemoryManagement.HANDY
        # self.ClassObjectMemoryManagement = ClassObjectMemoryManagement.SMART_PTR
        self.BindingStructure = BindingStructure.FLATTENED

projectConfig = ProjectConfig()


# Base binding information class
class BindingInfo:
    def __init__(self, cursor, parent):
        self.cursor = cursor
        self.parent = parent

        self.name = cursor.spelling
        self.type = cursor.type.spelling
        self.kind = cursor.kind
        self.displayname= cursor.displayname
        self.is_template_instance = self.displayname.endswith('>')

        self.indent_space = 4

        self.process()
    def process(self):
        pass

    def is_top_level(self):
        return isinstance(self.parent, ProjectInfo)
    
    def get_mangling_prefix(self):
        return ''
    
    def get_mangled_name(self):
        mangeled_name = self.get_mangling_prefix() + self.name
        parent_name = self.parent.get_mangled_name()
        if not parent_name == '':
            mangeled_name = parent_name + '::' + mangeled_name
        return mangeled_name

    def get_full_name(self):
        if self.is_top_level():
            return self.name
        return self.parent.name + '::' + self.name
    
    def get_binding_type(self):
        return 'UNKNOWN'
    
    def get_binding_prefix(self):
        return ''
    
    def get_binding_suffix(self):
        return ''
    
    def gather_binding_info(self):
        binding_info = {
            'binding_type': self.get_binding_type(),
            'full_name': self.get_full_name(),
            'mangled_name': self.get_mangled_name(),
            'name': self.name,
            'prefix': self.get_binding_prefix(),
            'suffix': self.get_binding_suffix(),
        }
        return binding_info
    # UNKONWN("BindingName", BindingFullName)
    def get_binding_template(self):
        return '%(prefix)s%(binding_type)s("%(name)s", &%(full_name)s)%(suffix)s'
    
    def get_binding(self, indent = 0):
        spaces = ' ' * (indent * self.indent_space)

        template = self.get_binding_template()
        binding_info = self.gather_binding_info()
        binding_content = template % binding_info

        binding = f'{spaces}{binding_content}'
        return binding




class EnumValueInfo(BindingInfo):
    def __init__(self, cursor, parent):
        super().__init__(cursor, parent)

    def process(self):
        self.name = self.cursor.spelling

    # .value("EnumName", Enum::EnumValueName)
    def get_binding_type(self):
        return 'value'
    
    def get_binding_template(self):
        return '.%(binding_type)s("%(name)s", %(full_name)s)'


class EnumInfo(BindingInfo):
    def __init__(self, cursor, parent):
        self.values = []
        super().__init__(cursor, parent)
    
    def process(self):
        for child in self.cursor.get_children():
            self.values.append(EnumValueInfo(child, self))
    
    def get_binding_type(self):
        return 'enum_'
    
    def get_binding_template(self):
        if projectConfig.BindingStructure == BindingStructure.STRUCTURAL:
            return '.%(binding_type)s<%(full_name)s>("%(name)s")'
        elif projectConfig.BindingStructure == BindingStructure.FLATTENED:
            return '%(binding_type)s<%(full_name)s>("%(mangled_name)s")'
        
    def get_binding(self, indent=0):
        binding = [super().get_binding(indent)]
        for value in self.values:
            binding.append(value.get_binding(indent + 1))

        return '\n'.join(binding) + ';'


# see: https://emscripten.org/docs/porting/connecting_cpp_and_javascript/embind.html#constants
class ConstantValueInfo(BindingInfo):
    def __init__(self, cursor, parent):
        super().__init__(cursor, parent)

    # constant("ConstantName", ConstantFullName);
    def get_binding_type(self):
        return 'constant'
    def get_binding_suffix(self):
        return ';'

    
# A static value defined in a file or namespace usually should not be exposed, and embind does not directly support this.
# If you do want to expose a static value, you should add it's getter and setter methods.  
class StaticValueInfo(BindingInfo):
    def __init__(self, cursor, parent):
        super().__init__(cursor, parent)
    


## A non-overloaded function binding is like:
# function("ClassName", &ClassName::FunctionName);

## An overloaded function binding is like:
# function("ClassName", select_overload<void(int)>(&ClassName::FunctionName));

# see https://emscripten.org/docs/porting/connecting_cpp_and_javascript/embind.html#overloaded-functions
class FunctionInfo(BindingInfo):
    def __init__(self, cursor, parent):
        self.return_type = ''
        self.args = []
        self.is_static = False
        self.is_overloaded = False

        super().__init__(cursor, parent)

    def process(self):
        self.return_type = self.cursor.result_type.spelling
        self.args = [arg.type.spelling for arg in self.cursor.get_arguments()]
        self.is_static = self.cursor.storage_class == StorageClass.STATIC
        if self.name.startswith('operator'):
            self.name = self.get_mapped_operator_name(self.name)

    def get_binding_type(self):
            return 'function'
   
    def gather_binding_info(self):
        return super().gather_binding_info() | {
            'return_type': self.return_type,
            'args': ', '.join(self.args),
        }

    def get_binding_template(self):
        if self.is_overloaded:
            return '%(prefix)s%(binding_type)s("%(name)s", select_overload<%(return_type)s(%(args)s)>(&%(full_name)s))%(suffix)s'
        else:
            return super().get_binding_template()
        
    def get_binding_suffix(self):
        return ';'
    
    def get_mapped_operator_name(self, operator_name):
        operator_name_map = {
            'operator=': '_assign',
            'operator++': '_increment',
            'operator--': '_decrement',
            'operator==': '_equals',
            'operator!=': '_not_equals',
            'operator+': '_plus',
            'operator+=': '_plus_assign',
            'operator-': '_minus',
            'operator-=':'_minus_assign',
            'operator*': '_multiply',
            'operator*=': '_multiply_assign',
            'operator/': '_divide',
            'operator/=': '_divide_assign',
            'operator%': '_modulo',
            'operator%=': '_modulo_assign',
            'operator^': '_xor',
            'operator^=': '_xor_assign',
            'operator&': '_and',
            'operator&=': '_and_assign',
            'operator|': '_or',
            'operator|=': '_or_assign',
            'operator<': '_less_than',
            'operator<=': '_less_than_equals',
            'operator>': '_greater_than',
            'operator>=': '_greater_than_equals',
            'operator<<': '_left_shift',
            'operator<<=': '_left_shift_assign',
            'operator>>': '_right_shift',
            'operator>>=': '_right_shift_assign',
            'operator&&': '_logical_and',
            'operator||': '_logical_or',
            'operator[]': '_subscript',
        }

        if operator_name_map.get(operator_name):
            return operator_name_map[operator_name]
        else:
            return operator_name

# A class that stores functions with the same name. i.e. overloaded functions
class FunctionHomonymic():
    def __init__(self):
        self.homonymic_functions:list[FunctionInfo] = []

    def add_function(self, method: FunctionInfo):
        
        if len(self.homonymic_functions) > 0:
            method.is_overloaded = True
        if len(self.homonymic_functions) == 1:
            self.homonymic_functions[0].is_overloaded = True

        self.homonymic_functions.append(method)

    def get_binding(self, indent):
        bindings = []
        for func in self.homonymic_functions:
            bindings.append(func.get_binding(indent)) 
        return '\n'.join(bindings)

# A class that stores function sets indexed by name
class Functions():
    def __init__(self):
        self.functionIndexedByName:dict[str, FunctionHomonymic] = {}

    def add_function(self, function: FunctionInfo):
        if function.name not in self.functionIndexedByName:
            self.functionIndexedByName[function.name] = FunctionHomonymic()
        self.functionIndexedByName[function.name].add_function(function)
    
    def count(self):
        return len(self.functionIndexedByName)

    def get_binding(self, indent):
        bindings = []
        for function in self.functionIndexedByName.values():
            bindings.append(function.get_binding(indent))
        return '\n'.join(bindings)


# see: https://emscripten.org/docs/porting/connecting_cpp_and_javascript/embind.html#class-properties
class ClassFieldInfo(BindingInfo):
    def __init__(self, cursor, parent):
        super().__init__(cursor, parent)

    def get_binding_prefix(self):
        return '.'
    def get_binding_type(self):
        return 'property'
    
    def get_return_value_policy(self):
        return 'return_value_policy::reference()'
    
    def gather_binding_info(self):
        return super().gather_binding_info() | {
            'return_value_policy': self.get_return_value_policy(),
        }
    
    # .property("FieldName", &ClassName::FieldName, return_value_policy::reference())
    def get_binding_template(self):
        return '%(prefix)s%(binding_type)s("%(name)s", &%(full_name)s, %(return_value_policy)s)'
    

# see: https://emscripten.org/docs/api_reference/bind.h.html#_CPPv4NK6class_14class_propertyEPKcP9FieldType
class ClassStaticValueInfo(BindingInfo):
    def __init__(self, cursor, parent):
        super().__init__(cursor, parent)
        self.is_constant = False

    def process(self):
        type = self.cursor.type
        if type.is_const_qualified():
            self.is_constant = True

        return super().process()

    def get_binding_type(self):
            return 'class_property'
    
    def get_binding_prefix(self):
        return '.'
    

# .function("FunctionName", &ClassName::FunctionName)
class ClassMethodInfo(FunctionInfo):
    def __init__(self, cursor, parent):
        self.is_virtual = False
        self.is_pure_virtual = False
        super().__init__(cursor, parent)

    def process(self):
        super().process()
        
        self.is_virtual = self.cursor.is_virtual_method()
        self.is_pure_virtual = self.cursor.is_pure_virtual_method()
   
    def get_binding_prefix(self):
        return '.'
    
 # .class_function("FunctionName", &ClassName::FunctionName)
class ClassStaticMethodInfo(ClassMethodInfo):
    def __init__(self, cursor, parent):
        super().__init__(cursor, parent)

    def get_binding_type(self):
        return 'class_function'
    
                        
class ConstructorInfo(ClassMethodInfo):
    def __init__(self, cursor, parent):
        super().__init__(cursor, parent)

    def get_binding_type(self):
        return 'constructor'
        
    def get_binding_template(self):
        return '%(prefix)s%(binding_type)s<%(args)s>()'
   
class Constructors(Functions):
    def __init__(self):
        super().__init__()

    def get_binding(self, indent):
        return super().get_binding(indent)
       
class ClassInfo(BindingInfo):
    def __init__(self, cursor, parent):
        self.constructors = Constructors()
        self.methods = Functions()
        self.fields = []
        self.enums = []
        self.structs = []
        self.classes = []
        self.static_values = []
        self.is_derived = False
        self.base_class_name = ''
        
        super().__init__(cursor, parent)

    def process(self):
        self.add_definations(self.cursor)

    def add_definations(self, cursor):
        # Only public members should be added
        filtered_children = [c for c in cursor.get_children() if c.access_specifier == AccessSpecifier.PUBLIC]

        for child in filtered_children:
            if child.kind == CursorKind.CXX_BASE_SPECIFIER:
                self.is_derived = True
                self.base_class_name = child.type.spelling
                pass
            elif child.kind == CursorKind.CONSTRUCTOR:
                self.constructors.add_function(ConstructorInfo(child, self))
            elif child.kind == CursorKind.VAR_DECL and child.storage_class == StorageClass.STATIC:
                self.static_values.append(ClassStaticValueInfo(child, self))
            elif child.kind == CursorKind.FIELD_DECL:
                self.fields.append(ClassFieldInfo(child, self))
            elif child.kind == CursorKind.CXX_METHOD:
                self.methods.add_function(ClassMethodInfo(child, self))
            elif child.kind == CursorKind.ENUM_DECL:
                self.enums.append(EnumInfo(child, self))
            elif child.kind == CursorKind.STRUCT_DECL:
                self.structs.append(StructInfo(child, self))
            elif child.kind == CursorKind.CLASS_DECL:
                self.classes.append(ClassInfo(child, self))
            elif child.kind == CursorKind.FUNCTION_TEMPLATE:
                print( f'Function template not yet supported: {child.displayname} in {self.name}')
            elif child.kind == CursorKind.CXX_ACCESS_SPEC_DECL:
                pass
            else:
                print(f'Ignored in class: {child.kind} name:{child.displayname} in {self.name}')

    def flatten_structure(self, root):
        if (root.definations.get(self.name) is not None):
            raise ValueError(f'Class name conflict: {self.name}')
        
        root.definations[self.name] = self
        for e in self.enums:
            if (root.definations.get(e.name) is not None):
                raise ValueError(f'Class name conflict: {e.name}')
        self.enums = []

        # Continue to flatten the nested classes
        for c in self.classes:
            c.flatten_structure(root)
        self.classes = []
        
        # and nested structs
        for c in self.structs:
            c.flatten_structure(root)
        self.structs = []
        
    def get_mangling_prefix(self):
        return 'C_'
    
    def get_binding_type(self):
        return 'class_'

    def gather_binding_info(self):
       return super().gather_binding_info() | {
           'base_class_name': self.base_class_name,
        }

    def get_binding_template(self):
        if self.is_derived:
            if projectConfig.BindingStructure == BindingStructure.FLATTENED:
                return '%(prefix)s%(binding_type)s<%(full_name)s, base<%(base_class_name)s>>("%(mangled_name)s")%(suffix)s'
            return '%(prefix)s%(binding_type)s<%(full_name)s, base<%(base_class_name)s>>("%(name)s")%(suffix)s'
        else:
            if projectConfig.BindingStructure == BindingStructure.FLATTENED:
                return '%(prefix)s%(binding_type)s<%(full_name)s>("%(mangled_name)s")%(suffix)s'
            return '%(prefix)s%(binding_type)s<%(full_name)s>("%(name)s")%(suffix)s'

    
    def get_binding(self, indent):
        spaces = ' ' * indent * 4
        bindings = []
        

        bindings.append(super().get_binding(indent))


        # Static values
        for static_value in self.static_values:
            bindings.append(static_value.get_binding(indent + 1))

        # Enums
        for enum in self.enums:
            bindings.append(enum.get_binding(indent + 1))

        # Constructors
        if (self.constructors.count() > 0):
            bindings.append(self.constructors.get_binding(indent + 1))
        
        # Fields
        for field in self.fields:
            bindings.append(field.get_binding(indent + 1))
        
        # Methods
        if (self.methods.count() > 0):
            bindings.append(self.methods.get_binding(indent + 1))
        
         # Nested classes
        for nested_class in self.classes:
            bindings.append(nested_class.get_binding(indent + 1))
        
        # Nested structs
        for nested_struct in self.structs:
            bindings.append(nested_struct.get_binding(indent + 1))
        
        # End of class
        bindings.append(f'{spaces};')
        
        return '\n'.join(bindings)
    
class StructInfo(ClassInfo):
    def __init__(self, cursor, parent):
        super().__init__(cursor, parent)

    def get_mangling_prefix(self):
        return 'S_'
    
    def get_binding_type(self):
        return 'value_object'
    
class NamespaceInfo(BindingInfo):
    def __init__(self, cursor, parent, project_dir):
        self.project_dir = project_dir

        self.definations:dict[str, BindingInfo] = {}
        self.namespaces:dict[str, NamespaceInfo] = {}
        super().__init__(cursor, parent)

    
    # Elements in a structure must be in a project level or a namespace level
    def scan_structure(self, cursor, definations:dict[str, BindingInfo], parent, project_dir):
        location = cursor.translation_unit.spelling
        filtered_children = [c for c in cursor.get_children() if c.kind != CursorKind.LINKAGE_SPEC and c.location.file.name == location and c.is_definition()]
        
        for child in filtered_children:

            if child.kind == CursorKind.NAMESPACE:
                if parent.namespaces.get(child.spelling) is None:
                    parent.namespaces[child.spelling] = NamespaceInfo(child, parent, project_dir)
                else:
                    parent.namespaces[child.spelling].add_definations(child)
            else:
                bindingInfo = None

                if child.kind == CursorKind.VAR_DECL:
                    if child.type.is_const_qualified():
                        bindingInfo = ConstantValueInfo(child, parent)
                    else:
                        bindingInfo = None
                elif child.kind == CursorKind.FUNCTION_DECL:
                    bindingInfo = FunctionInfo(child, parent)
                elif child.kind == CursorKind.CLASS_DECL:
                    bindingInfo = ClassInfo(child, parent)
                elif child.kind == CursorKind.STRUCT_DECL:
                    bindingInfo = StructInfo(child, parent)
                elif child.kind == CursorKind.ENUM_DECL:
                    bindingInfo = EnumInfo(child, parent)
                elif child.kind == CursorKind.CXX_ACCESS_SPEC_DECL:
                    bindingInfo = None

                else:
                    print(f'Ignored in structure: {child.kind} in {child.spelling}')
                
                
                if bindingInfo is not None:
                    if definations.get(bindingInfo.name) is None:
                        definations[bindingInfo.name] = bindingInfo
                    else:
                        print(f'Ignored duplicate defination: {bindingInfo.name}')
                        
    def process(self):
        self.scan_structure(self.cursor, self.definations, self, self.project_dir)

    def add_definations(self, cursor):
        self.scan_structure(cursor, self.definations, self, self.project_dir)

    def flatten_structure(self, root):
        # flatten the classes in current namespace
        removed_classes = []
        for key, value in self.definations.items():
            if not isinstance(value, ClassInfo):
                continue

            if root.definations.get(key) is not None:
                raise ValueError(f'Class name conflict: {key}')
            
            value.flatten_structure(root)
            removed_classes.append(key)

        for key in removed_classes:
            del self.definations[key]

        # flatten the nested namespaces
        for key, value in self.namespaces.items():
            value.flatten_structure(root)

    def get_mangled_name(self):
        mangled_name = 'N_' + self.cursor.spelling
        return self.parent.get_mangled_name() + mangled_name
    def get_binding(self, indent):
        if (projectConfig.BindingStructure == BindingStructure.FLATTENED):
            return self.get_binding_flattened(indent)
        elif (projectConfig.BindingStructure == BindingStructure.STRUCTURAL):
            return self.get_binding_structural(indent)
        else:
            raise ValueError(f'Unknown orgnize_structure: {self.orgnize_structure}')
    
    def get_binding_flattened(self, indent):
        spaces = ' ' * (indent * self.indent_space)
        bindings = [f'{spaces}// namespace: {self.name} ']
        # Add bindings for definitions in the namespace
        for definition in self.definations.values():
            bindings.append(definition.get_binding(indent + 1))

        # Add bindings for nested namespaces
        for namespace in self.namespaces.values():
            bindings.append(namespace.get_binding(indent + 1))

        # End of namespace
        bindings.append(f'{spaces};\n')

        return '\n'.join(bindings)

    # Since embind does not support namepace, keep this for future use
    def get_binding_structural(self, indent):
        spaces = ' ' * (indent * self.indent_space)
        bindings = []

        # Namespace declaration
        is_subnamespace = ''
        if self.is_top_level():
            is_subnamespace = ''
        else:
            is_subnamespace = '.'
        bindings.append(f'{spaces}{is_subnamespace}namespace_("{self.name}")')

        # Add bindings for definitions in the namespace
        for definition in self.definations.values():
            bindings.append(definition.get_binding(indent + 1))

        # Add bindings for nested namespaces
        for namespace in self.namespaces.values():
            bindings.append(namespace.get_binding(indent + 1))

        # End of namespace
        bindings.append(f'{spaces};\n')

        return '\n'.join(bindings)
    
class ProjectInfo(NamespaceInfo):
    def __init__(self, headers:list, dest_dir, parse_args=['-x', 'c++', '-std=c++17']):
        self.headers = headers
        self.dest_dir = dest_dir
        self.parse_args = parse_args

        self.includes = []

        fake_cursor = SimpleNamespace(spelling='MainModule', type=SimpleNamespace(spelling='root'), kind='root', displayname='root',)
        fake_cursor.canonical = fake_cursor
        
        super().__init__(fake_cursor, None, dest_dir)
    def process(self):
        
        for header in self.headers:
            index = Index.create(excludeDecls=True)
            tu = index.parse(header, self.parse_args, None,  TranslationUnit.PARSE_INCOMPLETE | TranslationUnit.PARSE_SKIP_FUNCTION_BODIES)
            self.scan_structure(tu.cursor, self.definations, self, self.dest_dir)

            relative_path = os.path.relpath(header, self.dest_dir)
            self.includes.append(relative_path)

    def flatten_structure(self, root):
        for key, value in self.namespaces.items():
            value.flatten_structure(root)

    def get_mangled_name(self):
        return ''
      
    def get_binding(self, indent):
        spaces = ' ' * (indent * self.indent_space)
        bindings = []

        # Include headers
        bindings.append('#include <emscripten/bind.h>')
        for header in self.includes:
            bindings.append(f'#include "{header}"')

        # Start of embind bindings
        bindings.append(f'\n{spaces}EMSCRIPTEN_BINDINGS({self.name}) {{')

        # Add bindings for definitions in the project
        for definition in self.definations.values():
            bindings.append(definition.get_binding(indent + 1))

        # Add bindings for nested namespaces
        for namespace in self.namespaces.values():
            bindings.append(namespace.get_binding(indent + 1))

        # End of embind bindings
        bindings.append(f'{spaces}}}\n')

        return '\n'.join(bindings)


def copy_files(src_dir, dest_dir):
    if os.path.exists(dest_dir):
        shutil.rmtree(dest_dir)
    shutil.copytree(src_dir, dest_dir)



def main():
    if len(sys.argv) != 3:
        print("Usage: python script.py <src_dir> <dest_dir>")
        return

    src_dir, dest_dir = sys.argv[1], sys.argv[2]
    dest_dir = os.path.abspath(dest_dir)
    # Step 1: Copy files
    copy_files(src_dir, dest_dir)
    
    # Step 2: Analyze headers
    headers = []
    for root, _, files in os.walk(dest_dir):
        for file in files:
            if file.endswith('.h'):
                path = os.path.join(root, file)
                headers.append(path)
                
    project_info = ProjectInfo(headers, dest_dir)
    if (projectConfig.BindingStructure == BindingStructure.FLATTENED):
        project_info.flatten_structure(project_info)
    
    binding_content = project_info.get_binding(0)
    with open(os.path.join(dest_dir, 'embind_bindings.cpp'), 'w') as f:
        f.write(binding_content)
    
    
    # generate_emcc_command(dest_dir, os.path.join(dest_dir, 'output.js'))
    # print(f"emcc --bind -O3 -std=c++17 -I{dest_dir} {dest_dir}/*.cpp {dest_dir}/embind_bindings.cpp -s WASM=1 -o {dest_dir}/output.js --embind-emit-tsd")


def generate_emcc_command(dest, output_file):
    files = os.listdir(dest)
    cpp_files = [f for f in files if f.endswith('.cpp')]
    
    if not cpp_files:
        print(f"Not found .app files in '{dest}' ")
        return
    
    cpp_files = [os.path.join(dest, f) for f in cpp_files]
    cpp_files_str = ' '.join(cpp_files)
    emcc_command = f"emcc {cpp_files_str} -o {output_file} --bind -O3 -std=c++17 -s WASM=1"
    
    print("Bindings generated. Compile with:\n")
    print(emcc_command)


if __name__ == "__main__":
    main()