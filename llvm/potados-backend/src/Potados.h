#ifndef LLVM_POTADOS_H
#define LLVM_POTADOS_H
#include "llvm/CodeGen/SelectionDAGNodes.h"
#include "llvm/Support/CodeGen.h"
#define GET_SDNODE_ENUM
#include "PotadosGenSDNodeInfo.inc"
#define GET_REGINFO_ENUM
#include "PotadosGenRegisterInfo.inc"
#define GET_INSTRINFO_ENUM
#include "PotadosGenInstrInfo.inc"
namespace llvm {
class FunctionPass;
class PotadosTargetMachine;
class PassRegistry;
class Target;
Target &getThePotadosTarget();
FunctionPass *createPotadosISelDag(PotadosTargetMachine &, CodeGenOptLevel);
void initializePotadosAsmPrinterPass(PassRegistry &);
void initializePotadosDAGToDAGISelLegacyPass(PassRegistry &);
} // namespace llvm
#endif
