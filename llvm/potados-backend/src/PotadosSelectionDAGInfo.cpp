#include "PotadosSelectionDAGInfo.h"

#define GET_SDNODE_DESC
#include "PotadosGenSDNodeInfo.inc"

using namespace llvm;

PotadosSelectionDAGInfo::PotadosSelectionDAGInfo()
    : SelectionDAGGenTargetInfo(PotadosGenSDNodeInfo) {}

PotadosSelectionDAGInfo::~PotadosSelectionDAGInfo() = default;
