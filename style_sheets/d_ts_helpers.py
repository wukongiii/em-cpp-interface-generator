"""
Helper functions specifically for TypeScript definition (.d.ts) generation
Contains functions used in d_ts.yaml template
"""

import shared_helpers as shared

def get_stl_container_emcc_type(stl_container, module_name='MainModule'):
    """Generate TypeScript type reference for STL containers from emcc types"""
    mangled_name = stl_container.get_mangled_name()
    return f"typeof {module_name}.prototype.{mangled_name}"

def get_emcc_constructor_type(class_meta, module_name='MainModule'):
    """Generate TypeScript constructor type reference from emcc types"""
    mangled_name = class_meta.get_mangled_name()
    return f"typeof {module_name}.prototype.{mangled_name}"

def generate_all_constants_references(namespaces, module_name='MainModule'):
    """Generate references to constants in MainModule"""
    constants = shared.collect_all_constants(namespaces)
    result = ''
    
    for constant in constants:
        # Reference the constant from MainModule
        result += f"        {constant.get_ast_name()}: typeof {module_name}.prototype.{constant.get_ast_name()};\n"
    
    return result

def build_hierarchical_structure_for_exported(namespace):
    """Build hierarchical structure for exported object types - d.ts specific version"""
    return shared.build_hierarchical_structure_base(namespace, exclude_constants=True)

def generate_all_namespaces_exported_types(namespaces, module_name='MainModule'):
    """Generate TypeScript types for exported object structure"""
    return shared.generate_namespace_content_recursive(namespaces, lambda ns: generate_namespace_exported_types(ns, module_name))

def generate_namespace_exported_types(namespace, module_name='MainModule'):
    """Generate TypeScript types for exported namespace object"""
    result = ''
    
    structure = build_hierarchical_structure_for_exported(namespace)
    result += generate_structure_exported_types(structure, 3, module_name)
    
    for nested_ns in namespace.namespaces.values():
        result += f"            {nested_ns.get_ast_name()}: {{\n"
        result += generate_namespace_exported_types(nested_ns, module_name)
        result += "            };\n"
    
    return result

def generate_structure_exported_types(structure, indent_level, module_name='MainModule'):
    """Generate TypeScript types for exported object structure using emcc types"""
    indent = '    ' * indent_level
    result = ''
    
    for name, data in structure.items():
        if data['children']:
            result += f"{indent}{name}: {{\n"
            result += generate_structure_exported_types(data['children'], indent_level + 1, module_name)
            result += f"{indent}}};\n"
        else:
            if data['type'] in ['ClassMeta', 'StructMeta']:
                # Reference the constructor type from MainModule
                result += f"{indent}{name}: typeof {module_name}.prototype.{data['mangled_name']};\n"
            elif data['type'] == 'EnumMeta':
                # Reference the enum type from MainModule  
                result += f"{indent}{name}: typeof {module_name}.prototype.{data['mangled_name']};\n"
    
    return result 