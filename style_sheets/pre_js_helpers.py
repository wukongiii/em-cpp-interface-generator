"""
Helper functions specifically for pre.js generation
Contains functions used in pre_js.yaml template
"""

import shared_helpers as shared

def generate_all_constants_content(namespaces):
    """Generate all constants as top-level items"""
    constants = shared.collect_all_constants(namespaces)
    result = ''
    
    for constant in constants:
        result += f"                {constant.get_ast_name()}: Module['{constant.get_ast_name()}'],\n"
    
    return result

def generate_all_namespaces_content(namespaces):
    """Generate all namespaces content"""
    return shared.generate_namespace_content_recursive(namespaces, generate_namespace_content)

def generate_namespace_content(namespace):
    """Generate namespace content with proper hierarchical structure (excluding constants)"""
    result = ''
    
    # Build hierarchical structure from mangled names (excluding constants)
    structure = shared.build_hierarchical_structure_base(namespace, exclude_constants=True)
    
    # Generate hierarchical content
    result += generate_structure_content(structure, 5)  # 5 levels of indentation for namespace content
    
    # Process nested namespaces recursively
    for nested_ns in namespace.namespaces.values():
        result += f"                    {nested_ns.get_ast_name()}: {{\n"
        result += generate_namespace_content_nested(nested_ns, 6)
        result += "                    },\n"
    
    return result

def generate_namespace_content_nested(namespace, indent_level):
    """Generate nested namespace content"""
    return shared.generate_nested_namespace_content(namespace, generate_structure_content, indent_level)

def generate_structure_content(structure, indent_level):
    """Generate content for hierarchical structure"""
    indent = '    ' * indent_level
    result = ''
    
    for name, data in structure.items():
        if data['children']:
            # Has children, create nested structure using Object.assign
            if data['mangled_name']:
                # Use Object.assign to merge base class with nested properties
                result += f"{indent}{name}: Object.assign(Module['{data['mangled_name']}'], {{\n"
                result += generate_structure_content(data['children'], indent_level + 1)
                result += f"{indent}}}),\n"
            else:
                # Pure namespace with no base type
                result += f"{indent}{name}: {{\n"
                result += generate_structure_content(data['children'], indent_level + 1)
                result += f"{indent}}},\n"
        else:
            # Leaf node, simple mapping
            if data['mangled_name']:
                result += f"{indent}{name}: Module['{data['mangled_name']}'],\n"
    
    return result 