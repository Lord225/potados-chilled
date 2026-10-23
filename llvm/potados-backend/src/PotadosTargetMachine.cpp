#include "PotadosTargetMachine.h"
#include "Potados.h"
#include "llvm/CodeGen/Passes.h"
#include "llvm/CodeGen/TargetLoweringObjectFileImpl.h"
#include "llvm/CodeGen/TargetPassConfig.h"
#include "llvm/MC/TargetRegistry.h"

using namespace llvm;

static constexpr StringLiteral PotadosDataLayout =
    "e-m:e-p:16:16-i32:16-i64:16-f32:16-f64:16-a:8-n8:16-S16";

static TargetOptions getPotadosTargetOptions(const TargetOptions &Options) {
  TargetOptions Result = Options;
  Result.MCOptions.AsmVerbose = false;
  return Result;
}

PotadosTargetMachine::PotadosTargetMachine(const Target &T, const Triple &TT,
                                           StringRef CPU, StringRef FS,
                                           const TargetOptions &Options,
                                           std::optional<Reloc::Model> RM,
                                           std::optional<CodeModel::Model> CM,
                                           CodeGenOptLevel OL, bool)
    : CodeGenTargetMachineImpl(
          T, PotadosDataLayout, TT, CPU.empty() ? "generic" : CPU, FS,
          getPotadosTargetOptions(Options), RM.value_or(Reloc::Static),
          getEffectiveCodeModel(CM, CodeModel::Small), OL),
      TLOF(std::make_unique<TargetLoweringObjectFileELF>()),
      Subtarget(TT, CPU.empty() ? "generic" : CPU, FS, *this) {
  initAsmInfo();
}

PotadosTargetMachine::~PotadosTargetMachine() = default;

namespace {
class PotadosPassConfig final : public TargetPassConfig {
public:
  PotadosPassConfig(PotadosTargetMachine &TM, PassManagerBase &PM)
      : TargetPassConfig(TM, PM) {}

  bool addInstSelector() override {
    addPass(createPotadosISelDag(getTM<PotadosTargetMachine>(), getOptLevel()));
    return false;
  }
};
} // namespace

TargetPassConfig *PotadosTargetMachine::createPassConfig(PassManagerBase &PM) {
  return new PotadosPassConfig(*this, PM);
}

extern "C" LLVM_EXTERNAL_VISIBILITY void LLVMInitializePotadosTarget() {
  RegisterTargetMachine<PotadosTargetMachine> X(getThePotadosTarget());
  PassRegistry &PR = *PassRegistry::getPassRegistry();
  initializePotadosAsmPrinterPass(PR);
  initializePotadosDAGToDAGISelLegacyPass(PR);
}
