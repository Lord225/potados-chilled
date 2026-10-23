#include "llvm/MC/TargetRegistry.h"
#include "llvm/TargetParser/Triple.h"

using namespace llvm;

namespace llvm {
Target &getThePotadosTarget() {
  static Target ThePotadosTarget;
  return ThePotadosTarget;
}
} // namespace llvm

namespace {
extern "C" void LLVMInitializePotadosTargetMC();
extern "C" void LLVMInitializePotadosTarget();
extern "C" void LLVMInitializePotadosAsmPrinter();

bool matchPotadosArch(Triple::ArchType Arch) {
  // Potados is out of tree, so it has no entry in LLVM's closed ArchType enum.
  // llc selects it explicitly with -march=potados.
  return Arch == Triple::UnknownArch;
}

struct PotadosTargetRegistration {
  PotadosTargetRegistration() {
    TargetRegistry::RegisterTarget(getThePotadosTarget(), "potados_chilled",
                                   "POTADOS Chilled 16-bit CPU", "Potados",
                                   matchPotadosArch);
    LLVMInitializePotadosTargetMC();
    LLVMInitializePotadosTarget();
    LLVMInitializePotadosAsmPrinter();
  }
};

PotadosTargetRegistration RegisterPotadosTarget;
} // namespace
