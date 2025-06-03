# Embind Generator

An automated code generator for creating [Emscripten](https://emscripten.org/) binding files from C++ headers. This tool analyzes C++ header files and generates binding code for multiple output formats, making it easier to expose C++ code to JavaScript.

## Purpose

[Emscripten](https://emscripten.org/docs/introducing_emscripten/about_emscripten.html) supports [two main approaches](https://emscripten.org/docs/porting/connecting_cpp_and_javascript/index.html) to expose C++ code to JavaScript:

- [Embind](https://emscripten.org/docs/porting/connecting_cpp_and_javascript/embind.html)
- [WebIDL Bindings](https://emscripten.org/docs/porting/connecting_cpp_and_javascript/WebIDL-Binder.html)

Both approaches require writing binding definitions to tell Emscripten how to expose C++ code to JavaScript. This process can be tedious and error-prone for large codebases.

**Embind Generator** automates this process by:
- Parsing C++ header files using libclang
- Analyzing class structures, functions, enums, and namespaces
- Generating binding code in multiple formats:
  - **Embind**: `.cpp` binding files for Emscripten
  - **TypeScript**: `.d.ts` definition files for type safety
  - **pre.js**: JavaScript helper files for structured exports
  - **WebIDL**: `.idl` files (planned)

## Installation

### Prerequisites

- Python 3.7 or higher
- libclang (installed automatically with the package)

### Install from Source

1. Clone the repository:
```bash
git clone <repository-url>
cd embind_generator
```

2. Create a virtual environment (recommended):
```bash
python -m venv .venv
# On Windows
.venv\Scripts\activate
# On Linux/macOS
source .venv/bin/activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

### Dependencies

The tool requires the following Python packages:
- `libclang` - For C++ code parsing
- `mako` - For template processing
- `pyyaml` - For configuration files

## Usage

### Basic Syntax

```bash
python em_cpp_interface_generator.py <src_dir> <dest_dir> [options]
```

### Command Line Options

- `src_dir`: Source directory containing C++ header files
- `dest_dir`: Destination directory for generated files
- `--style <style>`: Output format (default: `embind`)
  - `embind`: Generate Embind binding files (`.cpp`)
  - `d_ts`: Generate TypeScript definition files (`.d.ts`)
  - `pre_js`: Generate pre.js helper files (`.js`)
  - `webidl`: Generate WebIDL files (`.idl`) - planned
- `--output <filename>`: Custom output filename (optional)
- `--module-name <name>`: Module name for bindings (default: `MainModule`)
- `--project-name <name>`: Project name for imports (default: same as module-name)

### Examples

#### 1. Generate Embind Bindings

```bash
# Basic embind generation
python em_cpp_interface_generator.py ./include ./output --style embind

# With custom module name
python em_cpp_interface_generator.py ./include ./output --style embind --module-name MyGameEngine
```

This generates `embind_bindings.cpp` in the output directory.

#### 2. Generate TypeScript Definitions

```bash
# Basic TypeScript definitions
python em_cpp_interface_generator.py ./include ./output --style d_ts

# With custom module and project names
python em_cpp_interface_generator.py ./include ./output --style d_ts \
  --module-name GameModule --project-name GameEngine
```

This generates `bindings.d.ts` with imports like:
```typescript
import { GameModule } from './GameEngine';
```

#### 3. Generate pre.js Helper Files

```bash
# Generate JavaScript helper files
python em_cpp_interface_generator.py ./include ./output --style pre_js --module-name MyModule
```

This generates `pre.js` with structured JavaScript objects matching your C++ namespace hierarchy.

#### 4. Custom Output Filename

```bash
# Specify custom output filename
python em_cpp_interface_generator.py ./include ./output --style embind \
  --output my_custom_bindings.cpp
```

### Workflow Integration

#### With Emscripten Build

1. Generate embind bindings:
```bash
python em_cpp_interface_generator.py ./src ./build --style embind --module-name MyApp
```

2. Compile with emscripten:
```bash
emcc ./build/*.cpp ./build/embind_bindings.cpp -o ./dist/myapp.js \
  --bind -O3 -std=c++17 -s WASM=1 --embind-emit-tsd myapp.d.ts
```

#### With TypeScript Projects

1. Generate TypeScript definitions:
```bash
python em_cpp_interface_generator.py ./src ./types --style d_ts \
  --module-name MyApp --project-name myapp
```

2. Use in TypeScript:
```typescript
import { MyApp } from './myapp';
import * as bindings from './types/bindings';

// Use structured bindings with full type safety
const vector = new bindings.Vector2(1.0, 2.0);
```

## Configuration

### Module vs Project Names

- **Module Name** (`--module-name`): Used in the generated binding code
  - Embind: `EMSCRIPTEN_BINDINGS(ModuleName)`
  - TypeScript: Type references like `typeof ModuleName.prototype.ClassName`

- **Project Name** (`--project-name`): Used in import paths
  - TypeScript: `import { ModuleName } from './ProjectName'`
  - Allows different naming for imports vs. internal references

### Supported C++ Features

The generator supports:
- ✅ Classes and structs
- ✅ Member functions and static methods
- ✅ Constructors and destructors
- ✅ Public member variables
- ✅ Enums and enum classes
- ✅ Namespaces (including nested)
- ✅ Constants and static variables
- ✅ STL containers (vector, map)
- ✅ Function overloading
- ✅ Operator overloading

### Limitations

- ❌ Void pointers (not supported by Embind)
- ❌ Non-const references (not supported by Embind)
- ❌ Template functions
- ❌ Private/protected members
- ❌ Complex template specializations

## Best Practices

### 1. Start with Embind
- Embind offers better C++ feature support
- Generates TypeScript definitions automatically
- Better for modern C++ codebases

### 2. Project Structure
```
project/
├── include/           # C++ headers
├── src/              # C++ source files
├── bindings/         # Generated binding files
└── types/           # Generated TypeScript definitions
```

### 3. Iterative Development
1. Generate initial bindings
2. Test and identify issues
3. Fine-tune the generated code
4. Extend the generator for missing features

### 4. Memory Management
- Use smart pointers (`std::shared_ptr`, `std::unique_ptr`) when possible
- Be careful with raw pointers and object lifetimes
- Consider using `return_value_policy` for pointer returns

## Comparison: Embind vs WebIDL

| Feature                      | **Embind**                                                                                   | **WebIDL Binder**                                                                                   |
|------------------------------|----------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------|
| **Binding Definition**       | Defined in C++ files using `EMSCRIPTEN_BINDINGS` macros                                     | Defined in separate `.idl` files using WebIDL syntax                                                |
| **C++ Feature Support**      | Wide range: templates, smart pointers, `std::string`                                        | Limited: only basic C++ features expressible in WebIDL                                             |
| **TypeScript Support**       | Native support with `--embind-emit-tsd`                                                     | No native TypeScript support                                                                        |
| **Memory Management**        | Fine-grained control with smart pointer support                                             | Limited memory management options                                                                    |
| **Ease of Use**              | More verbose but flexible                                                                    | Simpler for basic bindings, less flexible                                                           |
| **Performance**              | Slightly higher overhead due to flexibility                                                  | Lower overhead for simple bindings                                                                  |

### When to Use Embind

- Complex C++ codebases with modern features
- Need for TypeScript integration
- Custom memory management requirements
- Dynamic binding needs

### When to Use WebIDL

- Simple, performance-critical applications
- Basic C++ interfaces
- Minimal binding requirements

## Contributing

We welcome contributions! Please feel free to submit issues and pull requests.

### Development Setup

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

[Specify your license here]

## Troubleshooting

### Common Issues

1. **libclang not found**: Make sure libclang is properly installed
2. **Parse errors**: Check that your C++ headers are valid and compile
3. **Missing symbols**: Verify that all dependencies are included
4. **Template issues**: Complex templates may need manual binding

### Getting Help

- Check the [Issues](link-to-issues) section
- Review the generated code for debugging
- Enable verbose output for detailed error messages
