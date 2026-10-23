#ifndef LLVM_Potados_TARGETMACHINE_H
#define LLVM_Potados_TARGETMACHINE_H

#include "PotadosSubtarget.h"
#include "llvm/CodeGen/CodeGenTargetMachineImpl.h"

namespace llvm {
class PotadosTargetMachine final : public CodeGenTargetMachineImpl {
  std::unique_ptr<TargetLoweringObjectFile> TLOF;
  PotadosSubtarget Subtarget;

public:
  PotadosTargetMachine(const Target &T, const Triple &TT, StringRef CPU,
                       StringRef FS, const TargetOptions &Options,
                       std::optional<Reloc::Model> RM,
                       std::optional<CodeModel::Model> CM, CodeGenOptLevel OL,
                       bool JIT);
  ~PotadosTargetMachine() override;

  const PotadosSubtarget *getSubtargetImpl(const Function &) const override {
    return &Subtarget;
  }
  TargetPassConfig *createPassConfig(PassManagerBase &PM) override;
  TargetLoweringObjectFile *getObjFileLowering() const override {
    return TLOF.get();
  }
};
} // namespace llvm

#endif
