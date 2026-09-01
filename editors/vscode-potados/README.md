# POTADOS Assembly for VS Code

Language support for the POTADOS Chilled assembler:

- syntax highlighting for instructions, pseudo-instructions, registers,
  directives, labels, numbers, strings, and comments;
- snippet completions for every instruction and pseudo-instruction;
- register and directive completion;
- completion for labels and `.equ` constants in the current file;
- bracket pairing and semicolon comment toggling.

The extension recognizes `.asm` and `.pasm` files. If another assembly
extension wins the `.asm` association, choose **Change Language Mode** and
select **POTADOS Assembly**.

## Run during development

Open this directory in VS Code and press `F5`, or create a VSIX from the
repository root:

```sh
cd editors/vscode-potados
npx @vscode/vsce package
code --install-extension potados-asm-0.1.0.vsix
```

Reload VS Code after installation. Completions appear automatically and can
also be opened with `Ctrl+Space`.
