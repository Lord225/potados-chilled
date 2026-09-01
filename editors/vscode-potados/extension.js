"use strict";

const vscode = require("vscode");

const registers = ["ZERO", "R0", "SP", "R1", "R2", "R3", "R4", "R5", "R6", "R7"];

const instructions = [
  ["NOP", "NOP", "No operation"],
  ["ADD", "ADD ${1:R2}, ${2:R2}, ${3:R3}", "Integer addition: DST = A + B"],
  ["SUB", "SUB ${1:R2}, ${2:R2}, ${3:R3}", "Integer subtraction: DST = A - B"],
  ["AND", "AND ${1:R2}, ${2:R2}, ${3:R3}", "Bitwise AND"],
  ["OR", "OR ${1:R2}, ${2:R2}, ${3:R3}", "Bitwise OR"],
  ["XOR", "XOR ${1:R2}, ${2:R2}, ${3:R3}", "Bitwise XOR"],
  ["NOT", "NOT ${1:R2}, ${2:R3}", "Bitwise NOT"],
  ["MUL", "MUL ${1:R2}, ${2:R2}, ${3:R3}", "Integer multiplication"],
  ["SGE", "SGE ${1:R2}, ${2:R2}, ${3:R3}", "Set if signed greater/equal"],
  ["SL", "SL ${1:R2}, ${2:R2}, ${3:R3}", "Set if signed less"],
  ["SE", "SE ${1:R2}, ${2:R2}, ${3:R3}", "Set if equal"],
  ["SNE", "SNE ${1:R2}, ${2:R2}, ${3:R3}", "Set if not equal"],
  ["SAE", "SAE ${1:R2}, ${2:R2}, ${3:R3}", "Set if unsigned above/equal"],
  ["SB", "SB ${1:R2}, ${2:R2}, ${3:R3}", "Set if unsigned below"],
  ["SH", "SH ${1:R2}, ${2:R3}, ${3:1}", "Logical shift by signed immediate"],
  ["ASH", "ASH ${1:R2}, ${2:R3}, ${3:1}", "Arithmetic shift by signed immediate"],
  ["ADDI", "ADDI ${1:R2}, ${2:1}", "Add signed immediate in place"],
  ["LLI", "LLI ${1:R2}, ${2:0}", "Load low immediate byte"],
  ["LUI", "LUI ${1:R2}, ${2:0x80}", "Load high immediate byte"],
  ["LD", "LD ${1:R3}, [${2:R2} + ${3:0}]", "Load a word from memory"],
  ["ST", "ST ${1:R3}, [${2:R2} + ${3:0}]", "Store a word to memory"],
  ["LDSP", "LDSP ${1:R2}, ${2:0}", "Load relative to SP"],
  ["STSP", "STSP ${1:R2}, ${2:0}", "Store relative to SP"],
  ["JGE", "JGE ${1:R2}, ${2:R3}, ${3:label}", "Jump if signed greater/equal"],
  ["JL", "JL ${1:R2}, ${2:R3}, ${3:label}", "Jump if signed less"],
  ["JE", "JE ${1:R2}, ${2:R3}, ${3:label}", "Jump if equal"],
  ["JNE", "JNE ${1:R2}, ${2:R3}, ${3:label}", "Jump if not equal"],
  ["JAE", "JAE ${1:R2}, ${2:R3}, ${3:label}", "Jump if unsigned above/equal"],
  ["JB", "JB ${1:R2}, ${2:R3}, ${3:label}", "Jump if unsigned below"],
  ["JMP", "JMP ${1:label}", "Unconditional jump"],
  ["JAL", "JAL ${1:R7}, ${2:label}", "Jump and save return address"],
  ["PUSH", "PUSH ${1:R2}", "Push register to stack"],
  ["POP", "POP ${1:R2}", "Pop stack into register"],
  ["JMPR", "JMPR ${1:R7}", "Jump to register"],
  ["JALR", "JALR ${1:R7}, ${2:R2}", "Jump to register and link"],
  ["FADD", "FADD ${1:R2}, ${2:R2}, ${3:R3}", "Floating-point addition"],
  ["FSUB", "FSUB ${1:R2}, ${2:R2}, ${3:R3}", "Floating-point subtraction"],
  ["FMUL", "FMUL ${1:R2}, ${2:R2}, ${3:R3}", "Floating-point multiplication"],
  ["FDIV", "FDIV ${1:R2}, ${2:R2}, ${3:R3}", "Floating-point division"],
  ["ITOF", "ITOF ${1:R2}, ${2:R3}", "Integer to float"],
  ["FTOI", "FTOI ${1:R2}, ${2:R3}", "Float to signed integer"],
  ["FTOU", "FTOU ${1:R2}, ${2:R3}", "Float to unsigned integer"],
  ["HALT", "HALT", "Halt the processor"]
];

const pseudos = [
  ["LI", "LI ${1:R2}, ${2:0x1234}", "Smart 16-bit immediate load"],
  ["LEA", "LEA ${1:R2}, ${2:label}", "Load a label address"],
  ["MOV", "MOV ${1:R2}, ${2:R3}", "Copy one register to another"],
  ["CLR", "CLR ${1:R2}", "Clear a register"],
  ["INC", "INC ${1:R2}", "Increment a register"],
  ["DEC", "DEC ${1:R2}", "Decrement a register"],
  ["NEG", "NEG ${1:R2}", "Negate a register"],
  ["J", "J ${1:label}", "Short spelling of JMP"],
  ["CALL", "CALL ${1:function}", "Call using R7 as the link register"],
  ["RET", "RET", "Return through R7"]
];

const directives = [
  [".org", ".org ${1:0x0000}", "Set the word address"],
  [".section", ".section ${1:name}, ${2:0x0000}", "Start a named section"],
  [".equ", ".equ ${1:NAME}, ${2:value}", "Define a constant"],
  [".word", ".word ${1:0x0000}", "Emit 16-bit word data"],
  [".dw", ".dw ${1:0x0000}", "Alias for .word"],
  [".byte", ".byte ${1:0}", "Emit byte-valued word data"],
  [".db", ".db ${1:0}", "Alias for .byte"],
  [".string", ".string \"${1:text}\"", "Emit a string"],
  [".space", ".space ${1:count}, ${2:0}", "Reserve or fill words"]
];

function completion(label, snippet, documentation, kind) {
  const item = new vscode.CompletionItem(label, kind);
  item.insertText = new vscode.SnippetString(snippet);
  item.documentation = new vscode.MarkdownString(documentation);
  item.detail = "POTADOS Assembly";
  return item;
}

function documentLabels(document) {
  const items = [];
  const seen = new Set();
  const labelPattern = /^\s*([A-Za-z_][A-Za-z0-9_]*)\s*:/;
  const constantPattern = /^\s*\.equ\s+([A-Za-z_][A-Za-z0-9_]*)\s*,/i;

  for (let line = 0; line < document.lineCount; line += 1) {
    const text = document.lineAt(line).text;
    const match = labelPattern.exec(text) || constantPattern.exec(text);
    if (!match || seen.has(match[1])) continue;
    seen.add(match[1]);
    const item = new vscode.CompletionItem(match[1], vscode.CompletionItemKind.Reference);
    item.detail = `POTADOS symbol · line ${line + 1}`;
    items.push(item);
  }
  return items;
}

function activate(context) {
  const selector = "potados-asm";
  const provider = vscode.languages.registerCompletionItemProvider(selector, {
    provideCompletionItems(document) {
      const instructionItems = instructions.map(([name, snippet, docs]) =>
        completion(name, snippet, docs, vscode.CompletionItemKind.Keyword)
      );
      const pseudoItems = pseudos.map(([name, snippet, docs]) =>
        completion(name, snippet, docs, vscode.CompletionItemKind.Snippet)
      );
      const directiveItems = directives.map(([name, snippet, docs]) =>
        completion(name, snippet, docs, vscode.CompletionItemKind.Keyword)
      );
      const registerItems = registers.map((name) =>
        completion(name, name, "POTADOS register", vscode.CompletionItemKind.Variable)
      );
      return [...instructionItems, ...pseudoItems, ...directiveItems, ...registerItems, ...documentLabels(document)];
    }
  }, ".");
  context.subscriptions.push(provider);
}

function deactivate() {}

module.exports = {activate, deactivate};
