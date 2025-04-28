
# What for?

[Emscripten](https://emscripten.org/docs/introducing_emscripten/about_emscripten.html) supports [two](https://emscripten.org/docs/porting/connecting_cpp_and_javascript/index.html) ways to expose C++ code to JavaScript:

- [Embind](https://emscripten.org/docs/porting/connecting_cpp_and_javascript/embind.html)
- [WebIDL Bindings](https://emscripten.org/docs/porting/connecting_cpp_and_javascript/WebIDL-Binder.html)

Both of them need to write something to tell Emscripten how to expose C++ code to JavaScript. Ref : [Binding C++ and JavaScript — WebIDL Binder and Embind](https://emscripten.org/docs/porting/connecting_cpp_and_javascript/Interacting-with-code.html#binding-c-and-javascript-webidl-binder-and-embind)

- For WebIDL, you need to write a `.idl` file and then to [generate it's glue files](https://emscripten.org/docs/porting/connecting_cpp_and_javascript/WebIDL-Binder.html#generating-the-bindings-glue-code). Compile the glue files together with the source code to generate final outputs.
- For Embind, you need to write an binding `.cpp` file, then compile it with the source code also.

This tool is for generating the intermediate files for WebIDL and Embind.

- For WebIDL, it generates a `.idl` file.(Planning...)
- For Embind, it generates a `.cpp` file.

## Best practices

- Consider WebIDL first.
- If WebIDL is not enought and you only need to deal with few projects, you can write your own bindings
- If you have multiple small and simple projects, you can use the Embind Generator to generate rough bindings for you, and later fine tune them.
- Add features to Embind Generator if you find it's not enough.


## Detailed comparison of Embind Generator and WebIDL(AI generated content)

| Feature                      | **Embind**                                                                                   | **WebIDL Binder**                                                                                   |
|------------------------------|----------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------|
| **Binding Definition**       | Defined directly within C++ source files using `EMSCRIPTEN_BINDINGS` macros.                 | Defined in separate `.idl` files using WebIDL syntax.                                                |
| **C++ Feature Support**      | Supports a wide range of C++ features, including templates, smart pointers, and `std::string`. | Limited to C++ features that can be expressed in WebIDL; complex features like smart pointers are not supported. |
| **TypeScript Definitions**   | Can generate TypeScript declaration files (`.d.ts`) using the `--embind-emit-tsd` flag.      | Does not natively support generating TypeScript definitions.                                         |
| **Memory Management**        | Provides fine-grained control over memory management, including support for smart pointers.  | Offers limited control over memory management.                                                       |
| **Ease of Use**              | More verbose but offers greater flexibility and control.                                     | Simpler for straightforward bindings but less flexible for complex scenarios.                        |
| **Performance Overhead**     | Slightly higher due to its flexibility and runtime type information.                         | Lower overhead, making it suitable for performance-critical applications with simple bindings.       |

## Scenarios Where Embind Excels Over WebIDL Binder

1. **Complex C++ Features**: If your project utilizes advanced C++ features like templates, smart pointers (`std::shared_ptr`, `std::unique_ptr`), or complex class hierarchies, Embind is better suited as it can handle these intricacies effectively.

2. **Custom Memory Management**: When you need explicit control over object lifetimes and memory management between C++ and JavaScript, Embind provides the necessary tools and policies to manage memory safely.

3. **TypeScript Integration**: For projects that require TypeScript support, Embind can generate `.d.ts` files, facilitating better integration and type safety in TypeScript applications.

4. **Dynamic Binding Requirements**: If your application requires dynamic binding capabilities or runtime type information, Embind's flexibility makes it the preferred choice.

## Choosing Between Embind and WebIDL Binder

- **Use Embind**: When working with complex C++ codebases, requiring advanced features, custom memory management, or TypeScript integration.

- **Use WebIDL Binder**: For simpler projects where performance is critical, and the C++ interfaces can be adequately described using WebIDL syntax.

In summary, while both Embind and WebIDL Binder are valuable tools for bridging C++ and JavaScript, Embind offers greater flexibility and feature support, making it suitable for complex and modern C++ applications.
