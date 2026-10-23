#ifndef LLVM_Potados_SELECTIONDAGINFO_H
#define LLVM_Potados_SELECTIONDAGINFO_H

#include "llvm/CodeGen/SelectionDAGTargetInfo.h"

namespace llvm {
class PotadosSelectionDAGInfo final : public SelectionDAGGenTargetInfo {
public:
  PotadosSelectionDAGInfo();
  ~PotadosSelectionDAGInfo() override;
};
} // namespace llvm

#endif
