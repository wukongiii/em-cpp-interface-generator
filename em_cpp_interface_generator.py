import sys
import os
import shutil
from clang.cindex import Type, Index, Cursor, CursorKind, TypeKind, AccessSpecifier, StorageClass, TranslationUnit
from types import SimpleNamespace
from enum import Enum

# region ====== Configuration ======
# see: https://emscripten.org/docs/porting/connecting_cpp_and_javascript/embind.html#object-ownership
class FunctionReturnValuePolicy(Enum):
    DEFAULT = 0
    TAKE_OWNERSHIP = 1
    REFERENCE = 2

# see:  https://emscripten.org/docs/porting/connecting_cpp_and_javascript/embind.html#memory-management
class ClassObjectMemoryManagement(Enum):
    HANDY = 0
    SMART_PTR = 1


######## Project default configurations ################
class ProjectConfig:
    def __init__(self):
        self.FuncReturnValuePolicy = FunctionReturnValuePolicy.REFERENCE
        self.ClassObjectMemoryManagement = ClassObjectMemoryManagement.HANDY
        # self.ClassObjectMemoryManagement = ClassObjectMemoryManagement.SMART_PTR

projectConfig = ProjectConfig()

# endregion


# region ============= Binding Generation ==============
# Base binding class
class BindingInfo:
    def __init__(self, cursor, parent):
        self.cursor = cursor
        self.parent = parent

        self.name = cursor.spelling
        self.type = cursor.type.spelling if hasattr(cursor, 'type') else ''
        self.kind = cursor.kind
        self.displayname= cursor.displayname if hasattr(cursor, 'displayname') else ''
        self.is_template_instance = self.displayname.endswith('>')

        self.should_be_ignored = False
        self.ignored_reason = ''

        self.indent_space = 4

        self.process()
    def process(self):
        pass

    def is_top_level(self):
        return isinstance(self.parent, ProjectInfo)
    
    # region ====== Names ======
    def get_name(self):
        return self.name
    
    def get_full_name_template(self):
        return '%(parent_name)s%(level_seperator)s%(name)s'

    def get_level_seperator(self):
        return '::'

    def get_full_name(self):
        if self.is_top_level():
            return self.name

        full_name_template = self.get_full_name_template()
        full_name_info = {
            'parent_name': self.parent.get_full_name(),
            'level_seperator': self.get_level_seperator(),
            'name': self.name,
        }
        return full_name_template % full_name_info
    
    # endregion

    # region ====== Mangled name ======
    def get_mangling_prefix(self):
        return ''
    
    def get_mangled_name(self):
        mangeled_name = self.get_mangling_prefix() + self.name
        parent_name = self.parent.get_mangled_name()
        if not parent_name == '':
            mangeled_name = parent_name + '__' + mangeled_name
        return mangeled_name

    # endregion

    # region ====== Types ======
    def get_type(self):
        return self.type

    # returns all relevant type names for the binding
    def get_all_type_names(self):
        return [self.type]
    
    # returns all relevant types for the binding
    def get_all_types(self) -> list[Type]:
        return [self.cursor.type]
    
    def get_binding_type(self):
        return 'UNKNOWN'
    
    # endregion

    # region ====== Binding ======
    def get_binding_prefix(self):
        return ''
    
    def get_binding_suffix(self):
        return ''
    
    def gather_binding_info(self):
        binding_info = {
            'binding_type': self.get_binding_type(), # class_ enum_ function etc.

            'name': self.get_name(),
            'full_name': self.get_full_name(),
            'type': self.get_type(),
            'mangled_name': self.get_mangled_name(),

            'prefix': self.get_binding_prefix(), # '.' or ''
            'suffix': self.get_binding_suffix(), # ';' or ''
        }
        return binding_info
    # UNKONWN("BindingName", BindingFullName)
    def get_binding_template(self):
        return '%(prefix)s%(binding_type)s("%(name)s", &%(full_name)s)%(suffix)s'
    
    def comment_content(self, content):
        return f'/*{content}*/'
    
    def get_binding(self, indent = 0):
        spaces = ' ' * (indent * self.indent_space)

        template = self.get_binding_template()
        binding_info = self.gather_binding_info()
        binding_content = template % binding_info

        if self.should_be_ignored:
            binding_content = self.comment_content(binding_content)
            reason = f'Ignored binding due to: {self.ignored_reason}'
            binding_content = f'// {reason}\n' + binding_content
            print(reason)

        # Add spaces for each line
        lines = binding_content.split('\n')
        lines = [f'{spaces}{line}' for line in lines]
        binding_content = '\n'.join(lines)

        # binding = f'{spaces}{binding_content}'
        return binding_content

    # endregion


# Class for TypeDef
class TypeDefInfo(BindingInfo):
    def __init__(self, cursor, parent):
        self.original_type_name = ''
        super().__init__(cursor, parent)

    def process(self):
        self.name = self.cursor.spelling
        self.original_type_name = self.cursor.type.get_canonical().spelling

    def get_all_type_names(self):
        return [self.original_type_name]
    
    def get_all_types(self) -> list[Type]:
        return [self.cursor.type.get_canonical()]
    
# Class for STL containers like vector, map, set, etc.
class STLContainerBindingInfo(BindingInfo):
    def __init__(self, cursor, parent):
        self.binding_type = ''
        self.template_args = ''
        self.arguments_combined = ''

        super().__init__(cursor, parent)
    def process(self):
        # sdt::vector<int, float> -> vector
        self.binding_type = self.name.split('<')[0].split('::')[-1]
        # sdt::vector<int, float> -> int, float
        self.template_args = self.name.split('<')[1].split('>')[0]
        # vector<int, float> -> IntFloat
        self.argument_combined = ''.join(arg.strip().capitalize() for arg in self.template_args.replace('::', '__').split(','))
        # vector<int, float> -> VectorIntFloat
        self.name = self.argument_combined
        pass
    def get_binding_type(self):
        return self.binding_type

    def get_binding_prefix(self):
        return ''
    
    def get_binding_suffix(self):
        return ';'
    
    def get_mangling_prefix(self):
        if self.binding_type == 'vector':
            return 'STL__V_'
        elif self.binding_type =='map':
            return 'STL__M_'
        elif self.binding_type =='set':
            return 'STL__S_'
        elif self.binding_type =='unordered_map':
            return 'STL__UM_'
        elif self.binding_type =='unordered_set':
            return 'STL__US_'
        else:
            return 'UNKNOWN__'

    def gather_binding_info(self):
        return super().gather_binding_info() | {
            'binding_type': self.binding_type,
            'template_args': self.template_args,
        }


    def get_binding_template(self):
        return '%(prefix)sregister_%(binding_type)s<%(template_args)s>("%(mangled_name)s")%(suffix)s'


# Class for EnumValue
class EnumValueInfo(BindingInfo):
    def __init__(self, cursor, parent):
        super().__init__(cursor, parent)

    def process(self):
        self.name = self.cursor.spelling

    # .value("EnumName", Enum::EnumValueName)
    def get_binding_type(self):
        return 'value'
    
    def get_binding_template(self):
        return '.%(binding_type)s("%(name)s", %(type)s::%(name)s)'

# Class for Enum
class EnumInfo(BindingInfo):
    def __init__(self, cursor, parent):
        self.values = []
        super().__init__(cursor, parent)
    
    def process(self):
        for child in self.cursor.get_children():
            self.values.append(EnumValueInfo(child, self))
    
    def get_binding_type(self):
        return 'enum_'

    def get_mangling_prefix(self):
        return 'E_'
    
    def get_binding_template(self):
        # using mangled name to avoid name conflict
        return '%(binding_type)s<%(type)s>("%(mangled_name)s")'
    
        ## using original name
        #return '.%(binding_type)s<%(type)s>("%(name)s")'
        
        
    def get_binding(self, indent=0):
        spaces = ' ' * (indent * self.indent_space)

        bindings = [super().get_binding(indent)]
        for value in self.values:
            bindings.append(value.get_binding(indent + 1))

        bindings.append(f'{spaces};')
        return '\n'.join(bindings)


# Class for constants
# see: https://emscripten.org/docs/porting/connecting_cpp_and_javascript/embind.html#constants
class ConstantValueInfo(BindingInfo):
    def __init__(self, cursor, parent):
        super().__init__(cursor, parent)

    # constant("ConstantName", ConstantFullName);
    def get_binding_type(self):
        return 'constant'
    def get_binding_suffix(self):
        return ';'
    
    def get_binding_template(self):
        return '%(prefix)s%(binding_type)s("%(name)s", %(full_name)s)%(suffix)s'

    
# A static value defined in a file or namespace usually should not be exposed, and embind does not directly support this.
# If you do want to expose a static value, you should add it's getter and setter methods.  
class StaticValueInfo(BindingInfo):
    def __init__(self, cursor, parent):
        super().__init__(cursor, parent)
    


# Class for functions
class FunctionInfo(BindingInfo):
    def __init__(self, cursor, parent):
        self.return_type = ''
        self.args = []
        self.args_count = 0

        self.is_static = False
        self.is_overloaded = False

        self.returns_raw_pointer = False
        self.takes_raw_pointer = False
        self.has_any_void_pointer = False
        self.has_any_nonconst_reference = False

        super().__init__(cursor, parent)

    def process(self):
        self.is_static = self.cursor.storage_class == StorageClass.STATIC

        self.return_type = self.cursor.result_type.spelling
        self.args = [arg.type.get_canonical().spelling for arg in self.cursor.get_arguments()]
        self.args_count = len(self.args)
        
        # Check if the function returns a raw pointer or takes a raw pointer as an argument, later should use different policy
        self.returns_raw_pointer = self.return_type.endswith('*')
        self.takes_raw_pointer = any(arg.endswith('*') for arg in self.args)

        # Check if the function has any void pointer or non-const reference, they are not supported by embind
        self.has_any_void_pointer = any(arg == 'void *' for arg in self.args) or self.return_type == 'void *'
        self.has_any_nonconst_reference = any(arg.endswith('&') and not arg.startswith('const') for arg in self.args)

        if  self.has_any_void_pointer:
            self.should_be_ignored = True
            self.ignored_reason = f'void pointer found in function(embind does not support) : {self.get_full_name()}'
        
        if self.has_any_nonconst_reference:
            self.should_be_ignored = True
            self.ignored_reason += f'non-const reference found in function(embind does not support) : {self.get_full_name()}'
        
        
    def get_binding_type(self):
            return 'function'
    
    def get_all_type_names(self):
        return self.args + [self.return_type]
    
    def get_all_types(self) -> list[Type]:
        return [self.cursor.result_type.get_canonical()] + [arg.type.get_canonical() for arg in self.cursor.get_arguments()]

    def gather_binding_info(self):

        # see: https://emscripten.org/docs/porting/connecting_cpp_and_javascript/embind.html#raw-pointers
        # ref:
        # Because raw pointers have unclear lifetime semantics, embind requires their use to be marked with either allow_raw_pointers or with a return_value_policy. 
        # If the function returns a pointer it is recommended to use a return_value_policy instead of the general allow_raw_pointers.
        pointer_policy = ''
        if self.takes_raw_pointer:
            pointer_policy = ', allow_raw_pointers()'
        if self.returns_raw_pointer:
            pointer_policy = ', return_value_policy::reference()'

        return super().gather_binding_info() | {
            'return_type': self.return_type,
            'args': ', '.join(self.args),
            'signature': self.type,
            'pointer_policy': pointer_policy,
        }


    ## A non-overloaded function binding is like:
    # function("ClassName", &ClassName::FunctionName);

    ## An overloaded function binding is like:
    # function("ClassName", select_overload<void(int)>(&ClassName::FunctionName));

    # see https://emscripten.org/docs/porting/connecting_cpp_and_javascript/embind.html#overloaded-functions

    def get_binding_template(self):
        if self.is_overloaded:
            return '%(prefix)s%(binding_type)s("%(name)s", select_overload<%(signature)s>(&%(full_name)s)%(pointer_policy)s)%(suffix)s'
        else:
            return '%(prefix)s%(binding_type)s("%(name)s", &%(full_name)s%(pointer_policy)s)%(suffix)s'
        
    def get_binding_suffix(self):
        return ';'
    
    def get_name(self):
        if self.name.startswith('operator'):
            return self.get_mapped_operator_name(self.name)
        return self.name

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

    def add_function(self, method: FunctionInfo, check_args_count = False):
        
        if len(self.homonymic_functions) > 0:
            method.is_overloaded = True
        if len(self.homonymic_functions) == 1:
            self.homonymic_functions[0].is_overloaded = True

        if check_args_count:
            for func in self.homonymic_functions:
                if func.args_count == method.args_count:
                    # emcc will pass if you keep it in the bindings, but later will throw an error in the runtime, like:
                    ## Uncaught BindingError: Cannot register multiple constructors with identical number of parameters  for class! 
                    ## Overload resolution is currently only performed using the parameter count, not actual type info!
                    method.should_be_ignored = True
                    method.ignored_reason = f'overloaded function with same amount of paramters(embind does not support): {method.get_full_name()}'

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

    def add_function(self, function: FunctionInfo, check_args_count = False):
        if function.name not in self.functionIndexedByName:
            self.functionIndexedByName[function.name] = FunctionHomonymic()
        self.functionIndexedByName[function.name].add_function(function, check_args_count)
    
    def count(self):
        return len(self.functionIndexedByName)

    def get_binding(self, indent):
        bindings = []
        for function in self.functionIndexedByName.values():
            bindings.append(function.get_binding(indent))
        return '\n'.join(bindings)

# Iterate each function in a Functions object
def FunctionBindingInfoIterator(functions:Functions):
    for function in functions.functionIndexedByName.values():
        for item in function.homonymic_functions:
            yield item

# see: https://emscripten.org/docs/porting/connecting_cpp_and_javascript/embind.html#class-properties
class ClassPropertyInfo(BindingInfo):
    def __init__(self, cursor, parent):
        super().__init__(cursor, parent)

    def process(self):
        super().process()
        if self.type == 'void *':
            self.should_be_ignored = True
            self.ignored_reason = f'void pointer found in class property: {self.get_full_name()}'

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
    
    def get_binding_suffix(self):
        return ''
    
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

    def add_function(self, function: FunctionInfo, check_args_count = True):
        super().add_function(function, check_args_count)
        
    def get_binding(self, indent):
        return super().get_binding(indent)
    
       
class ClassInfo(BindingInfo):
    def __init__(self, cursor, parent):
        self.constructors = Constructors()
        self.methods = Functions()
        self.fields:list[ClassPropertyInfo] = []
        self.enums:list[EnumInfo] = []
        self.structs:list[StructInfo] = []
        self.classes:list[ClassInfo] = []
        self.static_values:list[ClassStaticValueInfo] = []
        self.type_defs:list[TypeDefInfo] = []

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
            elif child.kind == CursorKind.DESTRUCTOR:
                pass
            elif child.kind == CursorKind.VAR_DECL and child.storage_class == StorageClass.STATIC:
                self.static_values.append(ClassStaticValueInfo(child, self))
            elif child.kind == CursorKind.FIELD_DECL:
                self.fields.append(ClassPropertyInfo(child, self))
            elif child.kind == CursorKind.CXX_METHOD:
                if child.storage_class == StorageClass.STATIC:
                    self.methods.add_function(ClassStaticMethodInfo(child, self))
                else:
                    self.methods.add_function(ClassMethodInfo(child, self))
            elif child.kind == CursorKind.ENUM_DECL:
                self.enums.append(EnumInfo(child, self))
            elif child.kind == CursorKind.STRUCT_DECL:
                self.structs.append(StructInfo(child, self))
            elif child.kind == CursorKind.CLASS_DECL:
                self.classes.append(ClassInfo(child, self))
            elif child.kind == CursorKind.TYPEDEF_DECL:
                self.type_defs.append(TypeDefInfo(child, self))
            elif child.kind == CursorKind.FUNCTION_TEMPLATE:
                print( f'Function template not yet supported: {child.displayname} in {self.name}')
            elif child.kind == CursorKind.CXX_ACCESS_SPEC_DECL:
                pass
            else:
                print(f'Ignored item: kind: {child.kind}, name: {child.displayname}, in class: {self.name}')

    # Unnest the nested classes and structs and enums
    def unnest_to_namespace(self, namespace):
        namespace.definations.append(self)

        # move enums
        namespace.definations.extend(self.enums)
        self.enums = []

        # Continue to flatten the nested classes
        for c in self.classes:
            c.unnest_to_namespace(namespace)
        self.classes = []
        
        # and nested structs
        for c in self.structs:
            c.unnest_to_namespace(namespace)
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
            # using mangled name
            return '%(prefix)s%(binding_type)s<%(type)s, base<%(base_class_name)s>>("%(mangled_name)s")%(suffix)s'
            
            # # using original name
            # return '%(prefix)s%(binding_type)s<%(type)s, base<%(base_class_name)s>>("%(name)s")%(suffix)s'
        else:
            # using mangled name
            return '%(prefix)s%(binding_type)s<%(type)s>("%(mangled_name)s")%(suffix)s'
            
            # # using original name
            # return '%(prefix)s%(binding_type)s<%(type)s>("%(name)s")%(suffix)s'

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

def ClassBindingInfoIterator(classInfo:ClassInfo):
    # plane members
    for item in classInfo.fields:
        yield item
    for item in classInfo.static_values:
        yield item
    for item in classInfo.enums:
        yield item
    for item in classInfo.type_defs:
        yield item

    # methods
    for func in FunctionBindingInfoIterator(classInfo.constructors):
        yield func
    for func in FunctionBindingInfoIterator(classInfo.methods):
        yield func

    # nested classes and structs
    for nested_struct in classInfo.structs:
        for item in ClassBindingInfoIterator(nested_struct):
            yield item
    for nested_class in classInfo.classes:
        for item in ClassBindingInfoIterator(nested_class):
            yield item

# NOT USED
# see: https://emscripten.org/docs/api_reference/bind.h.html#_CPPv4N12value_object5fieldEPKcM12InstanceType9FieldType
class StructFieldInfo(ClassPropertyInfo):
    def __init__(self, cursor, parent):
        super().__init__(cursor, parent)

    def get_binding_prefix(self):
        return '.'
    def get_binding_type(self):
        return 'field'
    
    # .field("FieldName", &StructName::FieldName)
    def get_binding_template(self):
        # return '%(prefix)s%(binding_type)s("%(name)s", &%(full_name)s)'
        return super().get_binding_template()
    
    
# see: https://emscripten.org/docs/api_reference/bind.h.html#value-structs
class StructInfo(ClassInfo):
    def __init__(self, cursor, parent):
        super().__init__(cursor, parent)

    def get_mangling_prefix(self):
        return 'S_'
    
    # def get_binding_type(self):
    #     return 'value_object'
    
class NamespaceInfo(BindingInfo):
    def __init__(self, cursor, parent, project_dir):
        self.project_dir = project_dir

        self.type_defs:list[TypeDefInfo] = []
        self.definations:list[BindingInfo] = []
        self.namespaces:dict[str, NamespaceInfo] = {}

        super().__init__(cursor, parent)

    
    # Elements in a structure must be in a project level or a namespace level
    def scan_structure(self, cursor, definations:list[BindingInfo], parent, project_dir):
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
                elif child.kind == CursorKind.TYPEDEF_DECL:
                    self.type_defs.append(TypeDefInfo(child, parent))
                elif child.kind == CursorKind.CXX_ACCESS_SPEC_DECL:
                    bindingInfo = None

                else:
                    print(f'Ignored item: kind: {child.kind}, name: {child.spelling}, in file: {child.location.file.name}')
                
                if bindingInfo is not None:
                    definations.append(bindingInfo)
                        
    def process(self):
        self.scan_structure(self.cursor, self.definations, self, self.project_dir)

    def add_definations(self, cursor):
        self.scan_structure(cursor, self.definations, self, self.project_dir)

    # flatten() is used to unnest the nested classes and structs
    def flatten(self):
        classes:list[ClassInfo] = []
        for _class in self.definations:
            # not class and not struct
            if not isinstance(_class, ClassInfo):
                continue
            
            classes.append(_class)
        
        # for the consistency of the code, remove the classes from the definations first, later classes will be added to the definations
        for _class in classes:
            self.definations.remove(_class)

        for _class in classes:
            _class.unnest_to_namespace(self)

        # flatten the nested namespaces
        for ns in self.namespaces.values():
            ns.flatten()

    def get_mangled_name(self):
        mangled_name = 'N_' + self.cursor.spelling
        return self.parent.get_mangled_name() + mangled_name
    def get_binding(self, indent):
        spaces = ' ' * (indent * self.indent_space)
        bindings = []
        bindings.append(f'{spaces}{{ using namespace {self.name};')
        
        # Add bindings for definitions in the namespace
        for definition in self.definations:
            bindings.append(definition.get_binding(indent + 1))

        # Add bindings for nested namespaces
        for namespace in self.namespaces.values():
            bindings.append(namespace.get_binding(indent + 1))

        bindings.append(f'{spaces}}} // namespace {self.name}')
        return '\n'.join(bindings)

def NamespaceBindingInfoIterator(namespace:NamespaceInfo):
    # plane members
    for item in namespace.type_defs:
        yield item

    for item in namespace.definations:
        if isinstance(item, ClassInfo):
            for class_item in ClassBindingInfoIterator(item):
                yield class_item
        elif isinstance(item, Functions):
            for function_item in FunctionBindingInfoIterator(item):
                yield function_item
        else:
            yield item

    # nested namespaces
    for nested_namespace in namespace.namespaces.values():
        for item in NamespaceBindingInfoIterator(nested_namespace):
            yield item  




class ProjectInfo(NamespaceInfo):
    def __init__(self, headers:list, dest_dir, parse_args=['-x', 'c++', '-std=c++17']):
        self.headers = headers
        self.dest_dir = dest_dir
        self.parse_args = parse_args

        self.includes = []
        self.stl_containers:list[STLContainerBindingInfo] = []

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

        bumper = ProjectBindingInfoPump(self)
        bumper.add_filter('STLContainerFilter', STLContainerFilter())
        bumper.pump()

        stl_container_filter:STLContainerFilter = bumper.get_filter('STLContainerFilter')
        for type in stl_container_filter.types_can_be_registered.values():
            bindingInfo = STLContainerBindingInfo(type, self)
            self.stl_containers.append(bindingInfo)

    def flatten(self):
        for ns in self.namespaces.values():
            ns.flatten()

    def get_mangled_name(self):
        return ''
      
    def get_binding(self, indent):
        spaces = ' ' * (indent * self.indent_space)
        bindings = []

        # Include headers
        bindings.append('#include <emscripten/bind.h>')
        for header in self.includes:
            bindings.append(f'#include "{header}"')

        bindings.append(f'{spaces}using namespace emscripten;')

        # Start of embind bindings
        bindings.append(f'\n{spaces}EMSCRIPTEN_BINDINGS({self.name}) {{')

        # Add bindings for STL containers
        bindings.append(f'{spaces}// STL containers')
        for stl_container in self.stl_containers:
            bindings.append(stl_container.get_binding(indent + 1))
        bindings.append(f'{spaces}// End of STL containers\n')

        # Add bindings for definitions in the project
        bindings.append(f'{spaces}// definitions')
        for definition in self.definations:
            bindings.append(definition.get_binding(indent + 1))
        bindings.append(f'{spaces}// End of definitions\n')

        # Add bindings for nested namespaces
        for namespace in self.namespaces.values():
            bindings.append(namespace.get_binding(indent + 1))

        # End of embind bindings
        bindings.append(f'{spaces}}}\n')

        return '\n'.join(bindings)



    
# Base class for binding info filters
class BindingInfoFilter:
    def __init__(self):
        pass
    def filter(self, bindingInfo:BindingInfo):
        pass

# Iterate BindingInfo in a project
class ProjectBindingInfoPump:
    def __init__(self, project:ProjectInfo):
        self.project = project
        self.filters:dict[str, BindingInfoFilter] = {}

    def add_filter(self, filter_name:str, filter:BindingInfoFilter):
        self.filters[filter_name] = filter

    def get_filter(self, filter_name:str):
        if filter_name in self.filters:
            return self.filters[filter_name]
        else:
            return None

    def pump(self):
        for item in NamespaceBindingInfoIterator(self.project):
            for filter in self.filters.values():
                filter.filter(item)

# filters types using supported stl containers
class STLContainerFilter(BindingInfoFilter):    
    def __init__(self):
        self.stl_containers_can_be_registered = [
            'std::vector',
            'std::map',
        ]

        self.types_can_be_registered:dict[str, Type] = {}

        super().__init__()
    def filter(self, bindingInfo:BindingInfo):
        for stl_type in self.stl_containers_can_be_registered:
            for binding_type in bindingInfo.get_all_types():
                if stl_type in binding_type.spelling:
                    if binding_type.kind in (TypeKind.LVALUEREFERENCE, TypeKind.RVALUEREFERENCE):
                        binding_type = binding_type.get_pointee()
                    self.types_can_be_registered[binding_type.spelling] = binding_type
                    pass


# endregion ========= Binding generation =========

def copy_files(src_dir, dest_dir):
    if os.path.exists(dest_dir):
        shutil.rmtree(dest_dir)
    shutil.copytree(src_dir, dest_dir)


import argparse
def main():
    parser = argparse.ArgumentParser(description='Embind generator')
    parser.add_argument('src_dir', type=str, help='Source directory')
    parser.add_argument('dest_dir', type=str, help='Destination directory')
    args = parser.parse_args()

    src_dir, dest_dir = args.src_dir, args.dest_dir
    src_dir = os.path.abspath(src_dir)
    dest_dir = os.path.abspath(dest_dir)


    # Step 1: Copy files
    # copy_files(src_dir, dest_dir)
    
    # Step 2: Analyze headers
    headers = []
    for root, _, files in os.walk(dest_dir):
        for file in files:
            if file.endswith('.h'):
                path = os.path.join(root, file)
                headers.append(path)
                
    project_info = ProjectInfo(headers, dest_dir)
    project_info.flatten()
    
    

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