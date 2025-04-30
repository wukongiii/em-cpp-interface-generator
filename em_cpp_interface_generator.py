import os
import shutil
from clang.cindex import Type, Index, Cursor, CursorKind, TypeKind, AccessSpecifier, StorageClass, TranslationUnit
from types import SimpleNamespace
from enum import Enum
from mako.template import Template
from mako.exceptions import RichTraceback
from mako.exceptions import text_error_template

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

# region ====== Style process ======
import yaml

style_sheets = {}
current_style_sheet = {}
def load_style_sheets():
    style_sheets = {
        'embind': None, # for embind
        'pre_js': None, # for pre.js to unmangle the name and restore the structure
        'd_ts': None, # for d.ts to export the types
        'webidl': None, # for WebIDL
    }
    
    for name in style_sheets.keys():
        with open(f'style_sheets/{name}.yaml', 'r') as file:
            style = yaml.safe_load(file)
            style_sheets[name] = style

    return style_sheets

def select_style_sheet(style_name):
    global current_style_sheet
    if style_sheets.get(style_name) == None:
        raise KeyError('Style sheet %s not found' % style_name)

    current_style_sheet = style_sheets[style_name]

style_sheets = load_style_sheets()
select_style_sheet('embind')

# endregion


# region ============= Meta process ==============
# Base Meta class
class MetaInfo:
    def __init__(self, cursor, parent):
        self.cursor = cursor
        self.parent = parent

        self.ast_name = cursor.spelling
        self.ast_type_name = cursor.type.spelling if hasattr(cursor, 'type') else ''
        self.ast_kind = cursor.kind
        self.ast_displayname= cursor.displayname if hasattr(cursor, 'displayname') else ''

        self.is_template_instance = self.ast_displayname.endswith('>')

        self.should_be_ignored = False
        self.ignored_reason = ''

        # self.indent_space = 4

        self.process()

    def is_top_level(self):
        return isinstance(self.parent, ProjectMeta)

    def process(self):
        pass

    # region ====== Style ======
    def get_style(self, style_name, recursive=True):
        # uses self's class name to find the style
        style = current_style_sheet.get(self.__class__.__name__)
        if style is not None and style_name in style:
            return style.get(style_name)
        
        if recursive:
            # not found, try parent's style
            for base_class in self.__class__.__bases__:
                if base_class is object:
                    continue
                    
                base_class_name = base_class.__name__
                parent_style = current_style_sheet.get(base_class_name)
                if parent_style is not None and style_name in parent_style:
                    return parent_style.get(style_name)
        
        return None

    # endregion

    def get_indent_space(self):
        return self.get_style('indent_space') or 4

    # region ====== Types ======
    def get_type_name(self):
        return self.ast_type_name

    # returns all relevant type names
    def get_all_relavant_type_names(self):
        return [self.ast_type_name]
    
    # returns all relevant types
    def get_all_relavant_types(self) -> list[Type]:
        return [self.cursor.type]
    
    # endregion
    
    # region ====== Names ======

    # name from AST
    def get_ast_name(self):
        return self.ast_name

    # name for tagging the meta
    def get_tagging_name(self):
        return self.ast_name
    
    # full name
    def get_full_name_template(self):
        return self.get_style('full_name_template') or\
             '%(parent_name)s%(seperator)s%(ast_name)s'

    def get_full_name_seperator(self):
        return self.get_style('full_name_seperator') or '::'

    def get_full_name(self):
        if self.is_top_level():
            return self.get_ast_name()

        full_name_template = self.get_full_name_template()
        full_name_info = {
            'parent_name': self.parent.get_full_name(),
            'seperator': self.get_full_name_seperator(),
            'ast_name': self.get_ast_name(),
            'tagging_name': self.get_tagging_name(),
        }
        return full_name_template % full_name_info
    
    def get_mangling_template(self):
        return self.get_style('mangling_template') or\
             '%(parent_mangled_name)s%(seperator)s%(type_prefix)s%(self_mangled_name)s'

    def get_mangling_seperator(self):
        return self.get_style('mangling_seperator') or '__'

    def get_mangling_prefix(self):
        return self.get_style('mangling_prefix') or ''
    
    def get_mangled_name(self):
        parent_mangled_name = self.parent.get_mangled_name()
        mangling_template = self.get_mangling_template()
        name_mangling_info = {
            'parent_mangled_name': parent_mangled_name,
            'self_mangled_name':self.get_ast_name(),
            'seperator': self.get_mangling_seperator() if not parent_mangled_name == '' else '',
            'type_prefix': self.get_mangling_prefix(),
        }
        mangeled_name = mangling_template % name_mangling_info
        return mangeled_name

    # endregion

   

    # region ====== Tagging ======
   
    def get_tagging_prefix(self):
        return self.get_style('tagging_prefix') or ''
    def get_tagging_type(self):
        return self.get_style('tagging_type') or 'UNKNOWN'
    
    def get_tagging_suffix(self):
        return self.get_style('tagging_suffix') or ''
    
    def gather_tagging_info(self):
        tagging_info = {
            'type_name': self.get_type_name(),
            'tagging_type': self.get_tagging_type(), # class_ enum_ function etc.

            'ast_name': self.get_ast_name(),
            'tagging_name': self.get_tagging_name(),
            'full_name': self.get_full_name(),
            'mangled_name': self.get_mangled_name(),

            'prefix': self.get_tagging_prefix(), # '.' or ''
            'suffix': self.get_tagging_suffix(), # ';' or ''
        }
        return tagging_info

    def get_comment_template(self):
        return self.get_style('comment_template') or\
            '/*%(content)s*/'
    def comment_content(self, content):
        comment_template = self.get_comment_template()
        comment_content = comment_template % {'content': content}
        return comment_content

    def insert_to_each_line(self, content:str, pos, insertion):
        lines = content.split('\n')
        result_lines = []
        
        for line in lines:
            actual_pos = pos
            if pos < 0:
                actual_pos = len(line) + pos
                
            actual_pos = max(0, min(actual_pos, len(line)))
            new_line = line[:actual_pos] + insertion + line[actual_pos:]
            result_lines.append(new_line)
        
        return '\n'.join(result_lines)
    
    # UNKONWN("TaggingName", FullName)
    def get_tagging_template(self):
        return self.get_style('tagging_template') or\
            '%(prefix)s%(tagging_type)s("%(tagging_name)s", &%(full_name)s)%(suffix)s'

    def tagging(self, indent = 0):
        spaces = ' ' * (indent * self.get_indent_space())

        template = self.get_tagging_template()
        tagging_info = self.gather_tagging_info()
        tagging_content = template % tagging_info

        if self.should_be_ignored:
            tagging_content = self.comment_content(tagging_content)
            reason = f'Ignored due to: {self.ignored_reason}'
            tagging_content = f'// {reason}\n' + tagging_content
            print(reason)

        # Add spaces for each line
        lines = tagging_content.split('\n')
        lines = [f'{spaces}{line}' for line in lines]
        tagging_content = '\n'.join(lines)

        return tagging_content

    # endregion


# Class for TypeDef
class TypeDefMeta(MetaInfo):
    def __init__(self, cursor, parent):
        self.original_type_name = ''
        super().__init__(cursor, parent)

    def process(self):
        self.ast_name = self.cursor.spelling
        self.original_type_name = self.cursor.type.get_canonical().spelling

    def get_all_type_names(self):
        return [self.original_type_name]
    
    def get_all_relavant_types(self) -> list[Type]:
        return [self.cursor.type.get_canonical()]
    
# Class for STL containers like vector, map, set, etc.
class STLContainerMeta(MetaInfo):
    def __init__(self, cursor, parent):
        self.container_type = ''
        self.template_args = ''
        self.arguments_combined = ''

        super().__init__(cursor, parent)
    def process(self):
        # sdt::vector<int, float> -> vector
        self.container_type = self.ast_name.split('<')[0].split('::')[-1]
        # sdt::vector<int, float> -> int, float
        self.template_args = self.ast_name.split('<')[1].split('>')[0]
        # vector<int, float> -> IntFloat
        self.argument_combined = ''.join(arg.strip().capitalize() for arg in self.template_args.replace('::', '__').split(','))
        # vector<int, float> -> VectorIntFloat
        self.ast_name = self.argument_combined
        pass
    def get_tagging_type(self):
        return self.container_type

    def get_tagging_suffix(self):
        return self.get_style('tagging_suffix') or ';'
    
    def get_mangling_prefix(self):
        mangling_prefix = self.get_style('mangling_prefix') or {
            'vector': 'STL__V_',
            'map': 'STL__M_',
            'set': 'STL__S_',
            'unordered_map': 'STL__UM_',
            'unordered_set': 'STL__US_',
        }
        return mangling_prefix.get(self.container_type) or 'UNKNOWN'

    def get_tagging_template(self):
        return self.get_style('tagging_template') or\
            '%(prefix)sregister_%(tagging_type)s<%(template_args)s>("%(mangled_name)s")%(suffix)s'
    
    def gather_tagging_info(self):
        return super().gather_tagging_info() | {
            'tagging_type': self.container_type,
            'template_args': self.template_args,
        }



# Class for EnumValue
class EnumValueMeta(MetaInfo):
    def __init__(self, cursor, parent):
        super().__init__(cursor, parent)

    def process(self):
        self.ast_name = self.cursor.spelling

    # .value("EnumName", Enum::EnumValueName)
    def get_tagging_type(self):
        return self.get_style('tagging_type') or 'value'
    
    def get_tagging_template(self):
        return self.get_style('tagging_template') or\
            '.%(tagging_type)s("%(tagging_name)s", %(type_name)s::%(ast_name)s)'

# Class for Enum
class EnumMeta(MetaInfo):
    def __init__(self, cursor, parent):
        self.values = []
        super().__init__(cursor, parent)
    
    def process(self):
        for child in self.cursor.get_children():
            self.values.append(EnumValueMeta(child, self))
    
    def get_tagging_type(self):
        return self.get_style('tagging_type') or 'enum_'

    def get_mangling_prefix(self):
        return self.get_style('mangling_prefix') or 'E_'
    
    def get_tagging_template(self):
        return self.get_style('tagging_template') or\
            '%(prefix)s%(tagging_type)s<%(type_name)s>("%(mangled_name)s")%(suffix)s'
        
        
    def tagging(self, indent=0):
        spaces = ' ' * (indent * self.get_indent_space())

        taggings = [super().tagging(indent)]
        for value in self.values:
            taggings.append(value.tagging(indent + 1))

        taggings.append(f'{spaces};')
        return '\n'.join(taggings)


# Class for constants
# see: https://emscripten.org/docs/porting/connecting_cpp_and_javascript/embind.html#constants
class ConstantValueMeta(MetaInfo):
    def __init__(self, cursor, parent):
        super().__init__(cursor, parent)

    # constant("ConstantName", ConstantFullName);
    def get_tagging_type(self):
        return self.get_style('tagging_type') or 'constant'
    def get_tagging_suffix(self):
        return self.get_style('tagging_suffix') or ';'
    
    def get_tagging_template(self):
        return self.get_style('tagging_template') or\
            '%(prefix)s%(tagging_type)s("%(tagging_name)s", %(full_name)s)%(suffix)s'

    
# A static value defined in a file or namespace usually should not be exposed, and embind does not directly support this.
# If you do want to expose a static value, you should add it's getter and setter methods.  
class StaticValueInfo(MetaInfo):
    def __init__(self, cursor, parent):
        super().__init__(cursor, parent)
    


# Class for functions
class FunctionMeta(MetaInfo):
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
        
        
    def get_tagging_type(self):
        return self.get_style('tagging_type') or 'function'
    
    def get_all_type_names(self):
        return self.args + [self.return_type]
    
    def get_all_relavant_types(self) -> list[Type]:
        return [self.cursor.result_type.get_canonical()] + [arg.type.get_canonical() for arg in self.cursor.get_arguments()]

    def gather_tagging_info(self):

        # see: https://emscripten.org/docs/porting/connecting_cpp_and_javascript/embind.html#raw-pointers
        # ref:
        # Because raw pointers have unclear lifetime semantics, embind requires their use to be marked with either allow_raw_pointers or with a return_value_policy. 
        # If the function returns a pointer it is recommended to use a return_value_policy instead of the general allow_raw_pointers.
        pointer_policy = ''
        if self.takes_raw_pointer:
            pointer_policy = ', allow_raw_pointers()'
        if self.returns_raw_pointer:
            pointer_policy = ', return_value_policy::reference()'

        return super().gather_tagging_info() | {
            'return_type': self.return_type,
            'args': ', '.join(self.args),
            'signature': self.ast_type_name,
            'pointer_policy': pointer_policy,
        }


    ## A non-overloaded function binding is like:
    # function("ClassName", &ClassName::FunctionName);

    ## An overloaded function binding is like:
    # function("ClassName", select_overload<void(int)>(&ClassName::FunctionName));

    # see https://emscripten.org/docs/porting/connecting_cpp_and_javascript/embind.html#overloaded-functions

    def get_tagging_template(self):
        template = self.get_style('tagging_template') or {
            'non_overloaded': '%(prefix)s%(tagging_type)s("%(tagging_name)s", &%(full_name)s%(pointer_policy)s)%(suffix)s',
            'overloaded': '%(prefix)s%(tagging_type)s("%(tagging_name)s", select_overload<%(signature)s>(&%(full_name)s)%(pointer_policy)s)%(suffix)s'
        }
        if self.is_overloaded:
            return template['overloaded']
        return template['non_overloaded']        

    def get_tagging_suffix(self):
        return self.get_style('tagging_suffix') or ';'
    
    def get_tagging_name(self):
        if self.ast_name.startswith('operator'):
            return self.get_mapped_operator_name(self.ast_name)
        return self.ast_name

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
        self.homonymic_functions:list[FunctionMeta] = []

    def add_function(self, method: FunctionMeta, check_args_count = False):
        
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
        

    def tagging(self, indent):
        taggings = []
        for func in self.homonymic_functions:
            taggings.append(func.tagging(indent)) 
        return '\n'.join(taggings)

# A class that stores function sets indexed by name
class Functions():
    def __init__(self):
        self.functionIndexedByName:dict[str, FunctionHomonymic] = {}

    def add_function(self, function: FunctionMeta, check_args_count = False):
        if function.ast_name not in self.functionIndexedByName:
            self.functionIndexedByName[function.ast_name] = FunctionHomonymic()
        self.functionIndexedByName[function.ast_name].add_function(function, check_args_count)
    
    def count(self):
        return len(self.functionIndexedByName)

    def tagging(self, indent):
        taggings = []
        for function in self.functionIndexedByName.values():
            taggings.append(function.tagging(indent))
        return '\n'.join(taggings)

# Iterate each function in a Functions object
def FunctionIterator(functions:Functions):
    for function in functions.functionIndexedByName.values():
        for item in function.homonymic_functions:
            yield item

# see: https://emscripten.org/docs/porting/connecting_cpp_and_javascript/embind.html#class-properties
class ClassPropertyMeta(MetaInfo):
    def __init__(self, cursor, parent):
        super().__init__(cursor, parent)

    def process(self):
        super().process()
        if self.ast_type_name == 'void *':
            self.should_be_ignored = True
            self.ignored_reason = f'void pointer found in class property: {self.get_full_name()}'

    def get_tagging_prefix(self):
        return self.get_style('tagging_prefix') or '.'
    def get_tagging_type(self):
        return self.get_style('tagging_type') or 'property'
    
    def get_return_value_policy(self):
        return self.get_style('return_value_policy') or\
            'return_value_policy::reference()'
    
    def gather_tagging_info(self):
        return super().gather_tagging_info() | {
            'return_value_policy': self.get_return_value_policy(),
        }
    
    # .property("FieldName", &ClassName::FieldName, return_value_policy::reference())
    def get_tagging_template(self):
        return self.get_style('tagging_template') or\
            '%(prefix)s%(tagging_type)s("%(tagging_name)s", &%(full_name)s, %(return_value_policy)s)'
    

# see: https://emscripten.org/docs/api_reference/bind.h.html#_CPPv4NK6class_14class_propertyEPKcP9FieldType
class ClassStaticValueMeta(MetaInfo):
    def __init__(self, cursor, parent):
        super().__init__(cursor, parent)
        self.is_constant = False

    def process(self):
        type = self.cursor.type
        if type.is_const_qualified():
            self.is_constant = True

        return super().process()

    def get_tagging_type(self):
        return self.get_style('tagging_type') or 'class_property'
    
    def get_tagging_prefix(self):
        return self.get_style('tagging_prefix') or '.'
    

# .function("FunctionName", &ClassName::FunctionName)
class ClassMethodMeta(FunctionMeta):
    def __init__(self, cursor, parent):
        self.is_virtual = False
        self.is_pure_virtual = False
        super().__init__(cursor, parent)

    def process(self):
        super().process()
        
        self.is_virtual = self.cursor.is_virtual_method()
        self.is_pure_virtual = self.cursor.is_pure_virtual_method()
   
    def get_tagging_prefix(self):
        return self.get_style('tagging_prefix') or '.'
    
    def get_tagging_suffix(self):
        return self.get_style('tagging_suffix') or ''
    
 # .class_function("FunctionName", &ClassName::FunctionName)
class ClassStaticMethodMeta(ClassMethodMeta):
    def __init__(self, cursor, parent):
        super().__init__(cursor, parent)

    def get_tagging_type(self):
        return self.get_style('tagging_type') or 'class_function'
    
                        
class ConstructorMeta(ClassMethodMeta):
    def __init__(self, cursor, parent):
        super().__init__(cursor, parent)

    def get_tagging_type(self):
        return self.get_style('tagging_type') or 'constructor'
        
    def get_tagging_template(self):
        return self.get_style('tagging_template') or\
            '%(prefix)s%(tagging_type)s<%(args)s>()'
   
class Constructors(Functions):
    def __init__(self):
        super().__init__()

    def add_function(self, function: FunctionMeta, check_args_count = True):
        super().add_function(function, check_args_count)
        
    def get_tagging(tagging, indent):
        return super().tagging(indent)
    
       
class ClassMeta(MetaInfo):
    def __init__(self, cursor, parent):
        self.constructors = Constructors()
        self.methods = Functions()
        self.fields:list[ClassPropertyMeta] = []
        self.enums:list[EnumMeta] = []
        self.structs:list[StructMeta] = []
        self.classes:list[ClassMeta] = []
        self.static_values:list[ClassStaticValueMeta] = []
        self.type_defs:list[TypeDefMeta] = []

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
                self.constructors.add_function(ConstructorMeta(child, self))
            elif child.kind == CursorKind.DESTRUCTOR:
                pass
            elif child.kind == CursorKind.VAR_DECL and child.storage_class == StorageClass.STATIC:
                self.static_values.append(ClassStaticValueMeta(child, self))
            elif child.kind == CursorKind.FIELD_DECL:
                self.fields.append(ClassPropertyMeta(child, self))
            elif child.kind == CursorKind.CXX_METHOD:
                if child.storage_class == StorageClass.STATIC:
                    self.methods.add_function(ClassStaticMethodMeta(child, self))
                else:
                    self.methods.add_function(ClassMethodMeta(child, self))
            elif child.kind == CursorKind.ENUM_DECL:
                self.enums.append(EnumMeta(child, self))
            elif child.kind == CursorKind.STRUCT_DECL:
                self.structs.append(StructMeta(child, self))
            elif child.kind == CursorKind.CLASS_DECL:
                self.classes.append(ClassMeta(child, self))
            elif child.kind == CursorKind.TYPEDEF_DECL:
                self.type_defs.append(TypeDefMeta(child, self))
            elif child.kind == CursorKind.FUNCTION_TEMPLATE:
                print( f'Function template not yet supported: {child.displayname} in {self.ast_name}')
            elif child.kind == CursorKind.CXX_ACCESS_SPEC_DECL:
                pass
            else:
                print(f'Ignored item: kind: {child.kind}, name: {child.displayname}, in class: {self.ast_name}')

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
        return self.get_style('mangling_prefix') or 'C_'

    def get_tagging_type(self):
        return self.get_style('tagging_type') or 'class_'

    def gather_tagging_info(self):
       return super().gather_tagging_info() | {
           'base_class_name': self.base_class_name,
        }

    def get_tagging_template(self):
        template = self.get_style('tagging_template') or {
            'derived': '%(prefix)s%(tagging_type)s<%(type_name)s, base<%(base_class_name)s>>("%(mangled_name)s")%(suffix)s',
            'non_derived': '%(prefix)s%(tagging_type)s<%(type_name)s>("%(mangled_name)s")%(suffix)s'
        }
        if self.is_derived:
            return template['derived']
        return template['non_derived']

    def tagging(self, indent):
        spaces = ' ' * indent * 4
        taggings = []
        
        taggings.append(super().tagging(indent))

        # Static values
        for static_value in self.static_values:
            taggings.append(static_value.tagging(indent + 1))

        # Enums
        for enum in self.enums:
            taggings.append(enum.tagging(indent + 1))

        # Constructors
        if (self.constructors.count() > 0):
            taggings.append(self.constructors.tagging(indent + 1))
        
        # Fields
        for field in self.fields:
            taggings.append(field.tagging(indent + 1))
        
        # Methods
        if (self.methods.count() > 0):
            taggings.append(self.methods.tagging(indent + 1))
        
         # Nested classes
        for nested_class in self.classes:
            taggings.append(nested_class.tagging(indent + 1))
        
        # Nested structs
        for nested_struct in self.structs:
            taggings.append(nested_struct.tagging(indent + 1))
        
        # End of class
        taggings.append(f'{spaces};')
        
        return '\n'.join(taggings)

def ClassMetaIterator(classInfo:ClassMeta):
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
    for func in FunctionIterator(classInfo.constructors):
        yield func
    for func in FunctionIterator(classInfo.methods):
        yield func

    # nested classes and structs
    for nested_struct in classInfo.structs:
        for item in ClassMetaIterator(nested_struct):
            yield item
    for nested_class in classInfo.classes:
        for item in ClassMetaIterator(nested_class):
            yield item

# NOT USED
# see: https://emscripten.org/docs/api_reference/bind.h.html#_CPPv4N12value_object5fieldEPKcM12InstanceType9FieldType
class StructFieldMeta(ClassPropertyMeta):
    def __init__(self, cursor, parent):
        super().__init__(cursor, parent)

    def get_tagging_prefix(self):
        return self.get_style('tagging_prefix') or '.'

    def get_tagging_type(self):
        return self.get_style('tagging_type') or 'field'
    
    # .field("FieldName", &StructName::FieldName)
    def get_tagging_template(self):
        # return '%(prefix)s%(tagging_type)s("%(tagging_name)s", &%(full_name)s)'
        return super().get_tagging_template()
    
    
# see: https://emscripten.org/docs/api_reference/bind.h.html#value-structs
class StructMeta(ClassMeta):
    def __init__(self, cursor, parent):
        super().__init__(cursor, parent)

    def get_mangling_prefix(self):
        return self.get_style('mangling_prefix') or 'S_'
    
    # def get_tagging_type(self):
    #     return 'value_object'
    
class NamespaceMeta(MetaInfo):
    def __init__(self, cursor, parent, project_dir):
        self.project_dir = project_dir

        self.type_defs:list[TypeDefMeta] = []
        self.definations:list[MetaInfo] = []
        self.namespaces:dict[str, NamespaceMeta] = {}

        super().__init__(cursor, parent)

    
    # Elements in a structure must be in a project level or a namespace level
    def scan_structure(self, cursor, definations:list[MetaInfo], parent, project_dir):
        location = cursor.translation_unit.spelling
        filtered_children = [c for c in cursor.get_children() if c.kind != CursorKind.LINKAGE_SPEC and c.location.file.name == location and c.is_definition()]
        
        for child in filtered_children:

            if child.kind == CursorKind.NAMESPACE:
                if parent.namespaces.get(child.spelling) is None:
                    parent.namespaces[child.spelling] = NamespaceMeta(child, parent, project_dir)
                else:
                    parent.namespaces[child.spelling].add_definations(child)
            else:
                metaInfo = None

                if child.kind == CursorKind.VAR_DECL:
                    if child.type.is_const_qualified():
                        metaInfo = ConstantValueMeta(child, parent)
                    else:
                        metaInfo = None
                elif child.kind == CursorKind.FUNCTION_DECL:
                    metaInfo = FunctionMeta(child, parent)
                elif child.kind == CursorKind.CLASS_DECL:
                    metaInfo = ClassMeta(child, parent)
                elif child.kind == CursorKind.STRUCT_DECL:
                    metaInfo = StructMeta(child, parent)
                elif child.kind == CursorKind.ENUM_DECL:
                    metaInfo = EnumMeta(child, parent)
                elif child.kind == CursorKind.TYPEDEF_DECL:
                    self.type_defs.append(TypeDefMeta(child, parent))
                elif child.kind == CursorKind.CXX_ACCESS_SPEC_DECL:
                    metaInfo = None

                else:
                    print(f'Ignored item: kind: {child.kind}, name: {child.spelling}, in file: {child.location.file.name}')
                
                if metaInfo is not None:
                    definations.append(metaInfo)
                        
    def process(self):
        self.scan_structure(self.cursor, self.definations, self, self.project_dir)

    def add_definations(self, cursor):
        self.scan_structure(cursor, self.definations, self, self.project_dir)

    # flatten() is used to unnest the nested classes and structs
    def flatten(self):
        classes:list[ClassMeta] = []
        for _class in self.definations:
            # not class and not struct
            if not isinstance(_class, ClassMeta):
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

    def get_mangling_prefix(self):
        return self.get_style('mangling_prefix') or 'N_'

    def tagging(self, indent):
        spaces = ' ' * (indent * self.get_indent_space())
        taggings = []
        taggings.append(f'{spaces}{{ using namespace {self.ast_name};')
        
        # Add tagging for definitions in the namespace
        for definition in self.definations:
            taggings.append(definition.tagging(indent + 1))

        # Add tagging for nested namespaces
        for namespace in self.namespaces.values():
            taggings.append(namespace.tagging(indent + 1))

        taggings.append(f'{spaces}}} // namespace {self.ast_name}')
        return '\n'.join(taggings)

def NamespaceMetaInfoIterator(namespace:NamespaceMeta):
    # plane members
    for item in namespace.type_defs:
        yield item

    for item in namespace.definations:
        if isinstance(item, ClassMeta):
            for class_item in ClassMetaIterator(item):
                yield class_item
        elif isinstance(item, Functions):
            for function_item in FunctionIterator(item):
                yield function_item
        else:
            yield item

    # nested namespaces
    for nested_namespace in namespace.namespaces.values():
        for item in NamespaceMetaInfoIterator(nested_namespace):
            yield item  




class ProjectMeta(NamespaceMeta):
    def __init__(self, headers:list, dest_dir, parse_args=['-x', 'c++', '-std=c++17']):
        self.headers = headers
        self.dest_dir = dest_dir
        self.parse_args = parse_args

        self.includes = []
        self.stl_containers:list[STLContainerMeta] = []

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

        bumper = ProjectMetaInfoPump(self)
        bumper.add_filter('STLContainerFilter', STLContainerFilter())
        bumper.pump()

        stl_container_filter:STLContainerFilter = bumper.get_filter('STLContainerFilter')
        for type in stl_container_filter.types_can_be_registered.values():
            metaInfo = STLContainerMeta(type, self)
            self.stl_containers.append(metaInfo)

    def flatten(self):
        for ns in self.namespaces.values():
            ns.flatten()

    def get_mangled_name(self):
        return ''
      
    def tagging(self, indent):
        
        templateContent = self.get_style('tagging_template')
        template = Template(templateContent)
        context = {
            'indent': indent,
            'module_name': self.ast_name,
            'includes': self.includes,
            'stl_containers': self.stl_containers,
            'definations': self.definations,
            'namespaces': self.namespaces.values(),
        }
        try:
            content = template.render(**context)
        except Exception as e:
            print(text_error_template().render())
            raise e
        return content

        spaces = ' ' * (indent * self.get_indent_space())
        taggings = []

        # Include headers
        taggings.append('#include <emscripten/bind.h>')
        for header in self.includes:
            taggings.append(f'#include "{header}"')

        taggings.append(f'{spaces}using namespace emscripten;')

        # Start of embind bindings
        taggings.append(f'\n{spaces}EMSCRIPTEN_BINDINGS({self.ast_name}) {{')

        # Add bindings for STL containers
        taggings.append(f'{spaces}// STL containers')
        for stl_container in self.stl_containers:
            taggings.append(stl_container.tagging(indent + 1))
        taggings.append(f'{spaces}// End of STL containers\n')

        # Add bindings for definitions in the project
        taggings.append(f'{spaces}// definitions')
        for definition in self.definations:
            taggings.append(definition.tagging(indent + 1))
        taggings.append(f'{spaces}// End of definitions\n')

        # Add bindings for nested namespaces
        for namespace in self.namespaces.values():
            taggings.append(namespace.tagging(indent + 1))

        # End of embind bindings
        taggings.append(f'{spaces}}}\n')

        return '\n'.join(taggings)



    
# Base class for binding info filters
class MetaInfoFilter:
    def __init__(self):
        pass
    def filter(self, metaInfo:MetaInfo):
        pass

# Iterate BindingInfo in a project
class ProjectMetaInfoPump:
    def __init__(self, project:ProjectMeta):
        self.project = project
        self.filters:dict[str, MetaInfoFilter] = {}

    def add_filter(self, filter_name:str, filter:MetaInfoFilter):
        self.filters[filter_name] = filter

    def get_filter(self, filter_name:str):
        if filter_name in self.filters:
            return self.filters[filter_name]
        else:
            return None

    def pump(self):
        for item in NamespaceMetaInfoIterator(self.project):
            for filter in self.filters.values():
                filter.filter(item)

# filters types using supported stl containers
class STLContainerFilter(MetaInfoFilter):    
    def __init__(self):
        self.stl_containers_can_be_registered = [
            'std::vector',
            'std::map',
        ]

        self.types_can_be_registered:dict[str, Type] = {}

        super().__init__()
    def filter(self, metaInfo:MetaInfo):
        for stl_type in self.stl_containers_can_be_registered:
            all_relavant_types = metaInfo.get_all_relavant_types()
            for used_types in all_relavant_types:
                if stl_type in used_types.spelling:
                    if used_types.kind in (TypeKind.LVALUEREFERENCE, TypeKind.RVALUEREFERENCE):
                        used_types = used_types.get_pointee()
                    self.types_can_be_registered[used_types.spelling] = used_types
                    pass


# endregion ========= Meta generation =========




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
                
    project_info = ProjectMeta(headers, dest_dir)
    project_info.flatten()
    
    

    binding_content = project_info.tagging(0)
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