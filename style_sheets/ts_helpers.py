"""
Helper functions specifically for TypeScript definition (.d.ts) generation
Contains functions used in d_ts.yaml template
"""

import shared_helpers as shared

def get_stl_container_emcc_type(stl_container, module_name='MainModule'):
    """Generate TypeScript type reference for STL containers from emcc types"""
    mangled_name = stl_container.get_mangled_name()
    return f"PossibleInstanceType<{module_name}['{mangled_name}']>"

def get_emcc_constructor_type(class_meta, module_name='MainModule'):
    """Generate TypeScript constructor type reference from emcc types"""
    mangled_name = class_meta.get_mangled_name()
    return f"PossibleInstanceType<{module_name}['{mangled_name}']>"

def generate_all_constants_references(namespaces, module_name='MainModule'):
    """Generate references to constants in MainModule"""
    constants = shared.collect_all_constants(namespaces)
    result = ''
    
    for constant in constants:
        # Reference the constant from MainModule
        result += f"        {constant.get_ast_name()}: {module_name}['{constant.get_ast_name()}'];\n"
    
    return result

def build_hierarchical_structure_for_exported(namespace):
    """Build hierarchical structure for exported object types - d.ts specific version"""
    return shared.build_hierarchical_structure_base(namespace, exclude_constants=True)

def generate_all_namespaces_exported_types(namespaces, module_name='MainModule', is_export_namespace=True, export_namespace_name='Restructured'):
    """Generate TypeScript types for all namespaces
    
    Args:
        namespaces: The namespaces to process
        module_name: The module name to reference
        is_export_namespace: Whether to use export keyword (true for export namespace, false for interface)
        export_namespace_name: The name of the export namespace to reference in interface mode
    """
    if not namespaces:
        return ''
    
    result = ''
    for namespace in namespaces:
        if is_export_namespace:
            result += f"        // {namespace.get_ast_name()} namespace\n"
            result += f"        export namespace {namespace.get_ast_name()} {{\n"
            result += generate_namespace_exported_types(namespace, module_name, is_export_namespace, export_namespace_name)
            result += "        }\n"
        else:
            result += f"        // {namespace.get_ast_name()} namespace\n"
            result += f"        {namespace.get_ast_name()}: {{\n"
            # For interface mode, pass the namespace name as the initial path
            result += generate_namespace_exported_types(namespace, module_name, is_export_namespace, export_namespace_name, namespace.get_ast_name())
            result += "        };\n"
    
    return result

def generate_namespace_exported_types(namespace, module_name='MainModule', is_export_namespace=True, export_namespace_name='Restructured', namespace_path=''):
    """Generate TypeScript types for exported namespace object
    
    Args:
        namespace: The namespace to process
        module_name: The module name to reference
        is_export_namespace: Whether to use export keyword for namespace (true for export namespace, false for interface)
        export_namespace_name: The name of the export namespace to reference in interface mode
        namespace_path: The current namespace path for nested types
    """
    result = ''
    
    structure = build_hierarchical_structure_for_exported(namespace)
    # Use the provided namespace_path directly, don't add namespace name again
    result += generate_structure_exported_types(structure, 3, module_name, is_export_namespace, export_namespace_name, namespace_path)
    
    for nested_ns in namespace.namespaces.values():
        # Build the nested namespace path
        nested_path = f"{namespace_path}.{nested_ns.get_ast_name()}" if namespace_path else nested_ns.get_ast_name()
        if is_export_namespace:
            result += f"        export namespace {nested_ns.get_ast_name()} {{\n"
            result += generate_namespace_exported_types(nested_ns, module_name, is_export_namespace, export_namespace_name, nested_path)
            result += "        }\n"
        else:
            result += f"            {nested_ns.get_ast_name()}: {{\n"
            result += generate_namespace_exported_types(nested_ns, module_name, is_export_namespace, export_namespace_name, nested_path)
            result += "            };\n"
    
    return result

def generate_structure_exported_types(structure, indent_level, module_name='MainModule', is_export_namespace=True, export_namespace_name='Restructured', namespace_path=''):
    """Generate TypeScript types for exported object structure using emcc types
    
    Args:
        structure: The structure to process
        indent_level: Current indentation level
        module_name: The module name to reference
        is_export_namespace: Whether to use export keyword (true for export namespace, false for interface)
        export_namespace_name: The name of the export namespace to reference in interface mode
        namespace_path: The current namespace path for nested types
    """
    indent = '    ' * indent_level
    result = ''
    
    for name, data in structure.items():
        prefix = "export type " if is_export_namespace else ""
        suffix = ";" if not is_export_namespace else ""
        
        if data['children']:
            # When there are children, create an intersection type that includes both
            # the base class/struct/enum and the nested properties
            if data.get('mangled_name'):
                if is_export_namespace:
                    # For export namespace with children, create both type and namespace
                    result += f"{indent}{prefix}{name} = PossibleInstanceType<{module_name}['{data['mangled_name']}']>;\n"
                    result += f"{indent}export namespace {name} {{\n"
                    result += generate_structure_exported_types(data['children'], indent_level + 1, module_name, is_export_namespace, export_namespace_name, f"{namespace_path}.{name}" if namespace_path else name)
                    result += f"{indent}}}\n"
                else:
                    # For interface, use intersection type with direct module reference
                    result += f"{indent}{name}: {module_name}['{data['mangled_name']}'] & {{\n"
                    result += generate_structure_exported_types(data['children'], indent_level + 1, module_name, is_export_namespace, export_namespace_name, f"{namespace_path}.{name}" if namespace_path else name)
                    result += f"{indent}}}{suffix}\n"
            else:
                # Pure namespace - handled by the namespace generator
                pass
        else:
            if data['type'] in ['ClassMeta', 'StructMeta', 'EnumMeta']:
                # Reference the type from MainModule or export namespace
                if is_export_namespace:
                    result += f"{indent}{prefix}{name} = PossibleInstanceType<{module_name}['{data['mangled_name']}']>;\n"
                else:
                    result += f"{indent}{name}: {module_name}['{data['mangled_name']}'];\n"
    
    return result