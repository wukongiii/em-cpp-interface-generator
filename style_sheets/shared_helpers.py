"""
Shared helper functions for embind_generator style sheets
Contains common functions used across multiple style templates (pre_js.yaml, d_ts.yaml, etc.)
"""

def get_stl_readable_name(stl_container):
    """Generate readable names for STL containers"""
    container_type = stl_container.container_type
    args_combined = stl_container.argument_combined
    
    if container_type == 'vector':
        return args_combined + 'List'
    elif container_type == 'map':
        return args_combined + 'Map'
    elif container_type == 'set':
        return args_combined + 'Set'
    elif container_type == 'unordered_map':
        return args_combined + 'UnorderedMap'
    elif container_type == 'unordered_set':
        return args_combined + 'UnorderedSet'
    else:
        return container_type + args_combined

def parse_mangled_name(mangled_name):
    """Parse mangled name to extract hierarchy information
    
    Format: parent_mangled_name + '__' + type_prefix + self_name
    Type prefixes: N_ (namespace), C_ (class), S_ (struct), E_ (enum)
    """
    parts = mangled_name.split('__')
    hierarchy = []
    
    for part in parts:
        if part.startswith('N_'):
            hierarchy.append(('namespace', part[2:]))
        elif part.startswith('C_'):
            hierarchy.append(('class', part[2:]))
        elif part.startswith('S_'):
            hierarchy.append(('struct', part[2:]))
        elif part.startswith('E_'):
            hierarchy.append(('enum', part[2:]))
        elif part.startswith('STL__'):
            hierarchy.append(('stl', part))
        else:
            # Plain name without prefix (likely root level)
            hierarchy.append(('plain', part))
    
    return hierarchy

def collect_all_constants(namespaces):
    """Collect all constants from all namespaces"""
    constants = []
    
    def collect_from_namespace(namespace):
        for defination in namespace.definations:
            if defination.__class__.__name__ == 'ConstantValueMeta':
                constants.append(defination)
        
        # Recursively collect from nested namespaces
        for nested_ns in namespace.namespaces.values():
            collect_from_namespace(nested_ns)
    
    for namespace in namespaces:
        collect_from_namespace(namespace)
    
    return constants

def build_hierarchical_structure_base(namespace, exclude_constants=True):
    """Build hierarchical structure based on mangled names
    
    Args:
        namespace: The namespace to process
        exclude_constants: Whether to exclude constants from the structure
    
    Returns:
        dict: Hierarchical structure dictionary
    """
    structure = {}
    
    # Group all definitions by their parent hierarchy
    for defination in namespace.definations:
        # Skip constants if requested
        if exclude_constants and defination.__class__.__name__ == 'ConstantValueMeta':
            continue
            
        mangled_name = defination.get_mangled_name()
        hierarchy = parse_mangled_name(mangled_name)
        
        # For items with hierarchy, check if they belong to current namespace
        if len(hierarchy) > 1 and hierarchy[0][1] != namespace.get_ast_name():
            continue
        
        # Skip if no hierarchy (top-level items)
        if len(hierarchy) <= 1:
            structure[defination.get_ast_name()] = {
                'mangled_name': defination.get_mangled_name(),
                'type': defination.__class__.__name__,
                'meta': defination,
                'children': {}
            }
            continue
        
        # Build nested structure, starting from the second level (skip namespace level)
        current = structure
        for i, (prefix_type, name) in enumerate(hierarchy[1:-1]):  # Skip namespace and self
            if name not in current:
                current[name] = {
                    'children': {},
                    'type': prefix_type,
                    'mangled_name': None,
                    'meta': None
                }
            current = current[name]['children']
        
        # Add the final item
        final_name = defination.get_ast_name()
        current[final_name] = {
            'mangled_name': defination.get_mangled_name(),
            'type': defination.__class__.__name__,
            'meta': defination,
            'children': {}
        }
    
    return structure

def generate_namespace_content_recursive(namespaces, content_generator_func, **kwargs):
    """Generate namespace content recursively
    
    Args:
        namespaces: List of namespaces to process
        content_generator_func: Function to generate content for each namespace
        **kwargs: Additional arguments to pass to content_generator_func
    
    Returns:
        str: Generated content
    """
    if not namespaces:
        return ''
        
    result = '\n'
    
    for i, namespace in enumerate(namespaces):
        result += f"        // {namespace.get_ast_name()} namespace\n"
        result += f"        {namespace.get_ast_name()}: {{\n"
        result += content_generator_func(namespace, **kwargs)
        result += "        }"
        if i < len(namespaces) - 1:
            result += ","
        result += "\n"
    
    return result

def generate_nested_namespace_content(namespace, content_generator_func, indent_level, **kwargs):
    """Generate nested namespace content with proper indentation
    
    Args:
        namespace: The namespace to process
        content_generator_func: Function to generate structure content
        indent_level: Current indentation level
        **kwargs: Additional arguments
    
    Returns:
        str: Generated content
    """
    indent = '    ' * indent_level
    result = ''
    
    # Build hierarchical structure
    structure = build_hierarchical_structure_base(namespace)
    
    # Generate hierarchical content
    result += content_generator_func(structure, indent_level, **kwargs)
    
    # Process nested namespaces recursively
    for nested_ns in namespace.namespaces.values():
        result += f"{indent}{nested_ns.get_ast_name()}: {{\n"
        result += generate_nested_namespace_content(nested_ns, content_generator_func, indent_level + 1, **kwargs)
        result += f"{indent}}},\n"
    
    return result 