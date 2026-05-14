bl_info = {
    "name":        "Node Dungeon Router",
    "author":      "Valikzant",
    "version":     (1, 0, 0),
    "blender":     (3, 0, 0),
    "location":    "Node Editor → N-Panel → Node Dungeon Router",
    "description": "Auto-layout and animated wire routing for any node tree",
    "category":    "Node",
}

# ! НАЧАЛО БЛОКА ИНФОРМАЦИЯ
# Node Dungeon Router — расширение для авто-раскладки нод и прокладки проводов
# Работает в любом нод-эдиторе: материал, геонодс, композитор, шейдер
# ! КОНЕЦ БЛОКА ИНФОРМАЦИЯ

import bpy
from collections import defaultdict, deque
import heapq
import sys
import io

# ! НАЧАЛО БЛОКА ПЕРЕМЕННЫЕ

BOO_IsAnimating_dG = False  # защита от двойного запуска

# ! КОНЕЦ БЛОКА ПЕРЕМЕННЫЕ


# ! НАЧАЛО БЛОКА КЛАССЫ

class CLS_NodeRouterProps_G(bpy.types.PropertyGroup):
    """Настройки расширения, хранятся в сцене"""

    INT_GridSize_dC: bpy.props.IntProperty(
        name        = "Grid Size",
        description = "Размер ячейки сетки (пикселей). Меньше = точнее, но медленнее",
        default     = 20,
        min         = 5,
        max         = 80,
    )

    INT_StepX_dC: bpy.props.IntProperty(
        name        = "Column Step X",
        description = "Горизонтальный шаг между колоннами нод",
        default     = 600,
        min         = 100,
        max         = 1200,
    )

    INT_StepY_dC: bpy.props.IntProperty(
        name        = "Row Step Y",
        description = "Вертикальный шаг между рядами нод",
        default     = 600,
        min         = 100,
        max         = 1200,
    )

    INT_PortSpacing_dC: bpy.props.IntProperty(
        name        = "Port Spacing",
        description = "Отступ виртуальных портов от краёв ноды",
        default     = 40,
        min         = 10,
        max         = 200,
    )

    INT_BarycenterPasses_dC: bpy.props.IntProperty(
        name        = "Barycenter Passes",
        description = "Количество проходов выравнивания по барицентру. Влияет на то, насколько ноды выстраиваются по соседям",
        default     = 20,
        min         = 1,
        max         = 100,
    )

    INT_MaxCrossings_dC: bpy.props.IntProperty(
        name        = "Max Crossings",
        description = "Максимальное кол-во пересечений проводов (первая попытка A*)",
        default     = 10,
        min         = 0,
        max         = 100,
    )

    INT_MaxCrossingsFallback_dC: bpy.props.IntProperty(
        name        = "Max Crossings (Fallback)",
        description = "Лимит пересечений при второй попытке A*, если первая не нашла путь",
        default     = 15,
        min         = 0,
        max         = 200,
    )

    BOO_AnimEnabled_dC: bpy.props.BoolProperty(
        name        = "Animate Wires",
        description = "Показывать анимацию роста проводов в реальном времени",
        default     = True,
    )

    FLO_AnimSpeed_dC: bpy.props.FloatProperty(
        name        = "Anim Speed (sec)",
        description = "Задержка между шагами анимации (секунд). Меньше = быстрее",
        default     = 0.02,
        min         = 0.001,
        max         = 0.5,
        step        = 0.5,
        precision   = 3,
    )

    # --- A* Costs ---
    FLO_CostTurn_dC: bpy.props.FloatProperty(
        name        = "Turn Penalty",
        description = "Штраф за каждый поворот провода. Выше = провода прямее, но могут идти длиннее",
        default     = 150.0,
        min         = 0.0,
        max         = 500.0,
        step        = 10,
        precision   = 1,
    )

    FLO_CostCrossing_dC: bpy.props.FloatProperty(
        name        = "Crossing Penalty",
        description = "Штраф за пересечение уже проложенного провода",
        default     = 50.0,
        min         = 0.0,
        max         = 500.0,
        step        = 10,
        precision   = 1,
    )

    FLO_CostNearPort_dC: bpy.props.FloatProperty(
        name        = "Near-Port Penalty",
        description = "Штраф за прохождение вплотную к порту чужой ноды. Выше = провода обходят порты дальше",
        default     = 150.0,
        min         = 0.0,
        max         = 500.0,
        step        = 10,
        precision   = 1,
    )

    # --- Grid & Margins ---
    INT_NodeMargin_dC: bpy.props.IntProperty(
        name        = "Node Margin (cells)",
        description = "Зазор вокруг каждой ноды в клетках сетки. Больше = провода не прижимаются к нодам",
        default     = 1,
        min         = 0,
        max         = 10,
    )

    INT_GridMargin_dC: bpy.props.IntProperty(
        name        = "Grid Margin (cells)",
        description = "Поле вокруг всей сцены в клетках. Нужно чтобы провода могли огибать крайние ноды",
        default     = 8,
        min         = 2,
        max         = 40,
    )

    # --- Wire Behaviour ---
    BOO_SimplifyPath_dC: bpy.props.BoolProperty(
        name        = "Simplify Path",
        description = "Убирать лишние рероуты на прямых участках. Выкл = оставлять все точки пути",
        default     = True,
    )


class CLS_NodeRouterPanel_G(bpy.types.Panel):
    """Панель в N-панели нод-эдитора"""
    bl_label      = "Node Dungeon Router"
    bl_idname     = "NODE_PT_node_router"
    bl_space_type = "NODE_EDITOR"
    bl_region_type = "UI"
    bl_category   = "Node Dungeon Router"

    def draw(self, context):
        objProps_iL = context.scene.nodeRouterProps

        layLayout_iL = self.layout

        # --- Статус ---
        if BOO_IsAnimating_dG:
            objBox_iL = layLayout_iL.box()
            objBox_iL.label(text="Routing in progress...", icon="TIME")
        else:
            layLayout_iL.operator(
                "node.run_router",
                text  = "Run Layout & Route",
                icon  = "NODETREE",
            )

        layLayout_iL.separator()

        # --- Layout ---
        objBox_iL = layLayout_iL.box()
        objBox_iL.label(text="Layout", icon="ALIGN_JUSTIFY")
        objBox_iL.prop(objProps_iL, "INT_StepX_dC")
        objBox_iL.prop(objProps_iL, "INT_StepY_dC")
        objBox_iL.prop(objProps_iL, "INT_BarycenterPasses_dC")

        layLayout_iL.separator()

        # --- Routing ---
        objBox_iL = layLayout_iL.box()
        objBox_iL.label(text="Routing", icon="IPO_BEZIER")
        objBox_iL.prop(objProps_iL, "INT_GridSize_dC")
        objBox_iL.prop(objProps_iL, "INT_PortSpacing_dC")
        objBox_iL.prop(objProps_iL, "INT_MaxCrossings_dC")
        objBox_iL.prop(objProps_iL, "INT_MaxCrossingsFallback_dC")

        layLayout_iL.separator()

        # --- Animation ---
        objBox_iL = layLayout_iL.box()
        objBox_iL.label(text="Animation", icon="PLAY")
        objBox_iL.prop(objProps_iL, "BOO_AnimEnabled_dC")
        objRowAnim_iL = objBox_iL.row()
        objRowAnim_iL.enabled = objProps_iL.BOO_AnimEnabled_dC
        objRowAnim_iL.prop(objProps_iL, "FLO_AnimSpeed_dC")

        layLayout_iL.separator()

        # --- A* Costs ---
        objBox_iL = layLayout_iL.box()
        objBox_iL.label(text="A* Costs", icon="DRIVER_DISTANCE")
        objBox_iL.prop(objProps_iL, "FLO_CostTurn_dC")
        objBox_iL.prop(objProps_iL, "FLO_CostCrossing_dC")
        objBox_iL.prop(objProps_iL, "FLO_CostNearPort_dC")

        layLayout_iL.separator()

        # --- Grid & Margins ---
        objBox_iL = layLayout_iL.box()
        objBox_iL.label(text="Margins", icon="SNAP_GRID")
        objBox_iL.prop(objProps_iL, "INT_NodeMargin_dC")
        objBox_iL.prop(objProps_iL, "INT_GridMargin_dC")

        layLayout_iL.separator()

        # --- Wire Behaviour ---
        objBox_iL = layLayout_iL.box()
        objBox_iL.label(text="Wire Behaviour", icon="MOD_WIREFRAME")
        objBox_iL.prop(objProps_iL, "BOO_SimplifyPath_dC")


class CLS_RunRouterOp_G(bpy.types.Operator):
    """Оператор запуска роутера — читает активный нод-эдитор"""
    bl_idname = "node.run_router"
    bl_label  = "Run Node Dungeon Router"

    def execute(self, context):
        global BOO_IsAnimating_dG

        if BOO_IsAnimating_dG:
            self.report({"WARNING"}, "Router is already running!")
            return {"CANCELLED"}

        # Получаем активный нод-дерево из любого нод-эдитора
        objSpace_iL = None
        for objArea_iP in context.screen.areas:
            if objArea_iP.type == "NODE_EDITOR":
                for objSpace_iP in objArea_iP.spaces:
                    if objSpace_iP.type == "NODE_EDITOR" and objSpace_iP.node_tree:
                        objSpace_iL = objSpace_iP
                        break
                if objSpace_iL:
                    break

        if not objSpace_iL or not objSpace_iL.node_tree:
            self.report({"ERROR"}, "No active node tree found in Node Editor")
            return {"CANCELLED"}

        objProps_iL = context.scene.nodeRouterProps
        FUN_LayoutNodes_G(
            objSpace_iL.node_tree,
            objProps_iL.INT_GridSize_dC,
            objProps_iL.INT_StepX_dC,
            objProps_iL.INT_StepY_dC,
            objProps_iL.INT_PortSpacing_dC,
            objProps_iL.INT_BarycenterPasses_dC,
            objProps_iL.INT_MaxCrossings_dC,
            objProps_iL.INT_MaxCrossingsFallback_dC,
            objProps_iL.BOO_AnimEnabled_dC,
            objProps_iL.FLO_AnimSpeed_dC,
            objProps_iL.FLO_CostTurn_dC,
            objProps_iL.FLO_CostCrossing_dC,
            objProps_iL.FLO_CostNearPort_dC,
            objProps_iL.INT_NodeMargin_dC,
            objProps_iL.INT_GridMargin_dC,
            objProps_iL.BOO_SimplifyPath_dC,
        )

        return {"FINISHED"}

# ! КОНЕЦ БЛОКА КЛАССЫ


# ! НАЧАЛО БЛОКА ФУНКЦИИ

def FUN_GetSocketIndex_G(objNode_iA, objSocket_iA):
    try:
        return list(objNode_iA.inputs).index(objSocket_iA) \
            if objSocket_iA in list(objNode_iA.inputs) \
            else list(objNode_iA.outputs).index(objSocket_iA)
    except ValueError:
        return -1


def FUN_ResolveFrom_G(objSocket_iA):
    objNode_iL = objSocket_iA.node
    if objNode_iL.bl_idname != "NodeReroute":
        return objSocket_iA
    if not objNode_iL.inputs[0].links:
        return objSocket_iA
    return FUN_ResolveFrom_G(objNode_iL.inputs[0].links[0].from_socket)


def FUN_ResolveTo_G(objSocket_iA):
    objNode_iL = objSocket_iA.node
    if objNode_iL.bl_idname != "NodeReroute":
        return objSocket_iA
    if not objNode_iL.outputs[0].links:
        return objSocket_iA
    return FUN_ResolveTo_G(objNode_iL.outputs[0].links[0].to_socket)


def FUN_BuildTopoDepth_G(objTree_iA):
    arrNodes_iL  = [n for n in objTree_iA.nodes if n.bl_idname != "NodeReroute"]
    ditInDeg_iL  = {n.name: 0 for n in arrNodes_iL}
    ditEdges_iL  = defaultdict(set)

    for objNode_iP in arrNodes_iL:
        setFrom_iP = set()
        for objInput_iP in objNode_iP.inputs:
            for objLink_iP in objInput_iP.links:
                objFrom_iP = FUN_ResolveFrom_G(objLink_iP.from_socket).node
                if objFrom_iP.name != objNode_iP.name:
                    setFrom_iP.add(objFrom_iP.name)
        for strFrom_iP in setFrom_iP:
            ditEdges_iL[strFrom_iP].add(objNode_iP.name)
            ditInDeg_iL[objNode_iP.name] += 1

    queQueue_iL  = deque([n for n, d in ditInDeg_iL.items() if d == 0])
    ditDepth_iR  = {n: 0 for n in ditInDeg_iL}

    while queQueue_iL:
        strCur_iP = queQueue_iL.popleft()
        for strNext_iP in ditEdges_iL[strCur_iP]:
            ditDepth_iR[strNext_iP] = max(
                ditDepth_iR[strNext_iP],
                ditDepth_iR[strCur_iP] + 1
            )
            ditInDeg_iL[strNext_iP] -= 1
            if ditInDeg_iL[strNext_iP] == 0:
                queQueue_iL.append(strNext_iP)

    return ditDepth_iR


def FUN_GetAvgNeighborY_G(objNode_iA, ditCurrentY_iA):
    arrY_iL = []
    for objInput_iP in objNode_iA.inputs:
        for objLink_iP in objInput_iP.links:
            objFrom_iP = FUN_ResolveFrom_G(objLink_iP.from_socket).node
            if objFrom_iP.name in ditCurrentY_iA:
                arrY_iL.append(ditCurrentY_iA[objFrom_iP.name])
    for objOutput_iP in objNode_iA.outputs:
        for objLink_iP in objOutput_iP.links:
            objTo_iP = FUN_ResolveTo_G(objLink_iP.to_socket).node
            if objTo_iP.name in ditCurrentY_iA:
                arrY_iL.append(ditCurrentY_iA[objTo_iP.name])
    return sum(arrY_iL) / len(arrY_iL) if arrY_iL else 0.0


def FUN_SimplifyPath_G(arrPath_iA):
    if len(arrPath_iA) <= 2:
        return arrPath_iA
    arrSimplified_iR = [arrPath_iA[0]]
    for intI_iP in range(1, len(arrPath_iA) - 1):
        tupPrev_iP = arrPath_iA[intI_iP - 1]
        tupCurr_iP = arrPath_iA[intI_iP]
        tupNext_iP = arrPath_iA[intI_iP + 1]
        intDx1_iP, intDy1_iP = tupCurr_iP[0] - tupPrev_iP[0], tupCurr_iP[1] - tupPrev_iP[1]
        intDx2_iP, intDy2_iP = tupNext_iP[0] - tupCurr_iP[0], tupNext_iP[1] - tupCurr_iP[1]
        if (intDx1_iP, intDy1_iP) != (intDx2_iP, intDy2_iP):
            arrSimplified_iR.append(tupCurr_iP)
    arrSimplified_iR.append(arrPath_iA[-1])
    return arrSimplified_iR


def FUN_AStar_G(
    tupStart_iA, tupEnd_iA,
    arrGrid_iA, arrDistMap_iA,
    intSizeX_iA, intSizeY_iA,
    intMaxCrossings_iA=15,
    floCostTurn_iA=20.0,
    floCostCrossing_iA=15.0,
    floCostNearPort_iA=20.0,
):
    def fun_heuristic(tupA_iA, tupB_iA):
        return abs(tupA_iA[0] - tupB_iA[0]) + abs(tupA_iA[1] - tupB_iA[1])

    arrOpenSet_iL = []
    heapq.heappush(arrOpenSet_iL, (0, tupStart_iA[0], tupStart_iA[1], 0, -1))
    ditCameFrom_iL = {}
    ditGScore_iL   = {(tupStart_iA[0], tupStart_iA[1], 0): 0}

    while arrOpenSet_iL:
        _, intCx_iP, intCy_iP, intCCross_iP, intPrevDir_iP = heapq.heappop(arrOpenSet_iL)

        if (intCx_iP, intCy_iP) == tupEnd_iA:
            arrPath_iR = []
            tupCurr_iP = (intCx_iP, intCy_iP, intCCross_iP)
            while tupCurr_iP in ditCameFrom_iL:
                arrPath_iR.append((tupCurr_iP[0], tupCurr_iP[1]))
                tupCurr_iP = ditCameFrom_iL[tupCurr_iP]
            arrPath_iR.append(tupStart_iA)
            return arrPath_iR[::-1]

        for intI_iP, (intDx_iP, intDy_iP) in enumerate([(0, 1), (0, -1), (1, 0), (-1, 0)]):
            intNx_iP, intNy_iP = intCx_iP + intDx_iP, intCy_iP + intDy_iP
            if not (0 <= intNx_iP < intSizeX_iA and 0 <= intNy_iP < intSizeY_iA):
                continue

            intCellVal_iP  = arrGrid_iA[intNy_iP][intNx_iP]
            intNewCross_iP = intCCross_iP
            floMoveCost_iP = 1.0

            if intCellVal_iP == 1:
                continue
            if intCellVal_iP == 3 and (intNx_iP, intNy_iP) != tupStart_iA and (intNx_iP, intNy_iP) != tupEnd_iA:
                continue
            if intCellVal_iP == 5:
                booNearStart_iP = abs(intNx_iP - tupStart_iA[0]) <= 1 and abs(intNy_iP - tupStart_iA[1]) <= 1
                booNearEnd_iP   = abs(intNx_iP - tupEnd_iA[0]) <= 1 and abs(intNy_iP - tupEnd_iA[1]) <= 1
                if not booNearStart_iP and not booNearEnd_iP:
                    floMoveCost_iP += floCostNearPort_iA

            booIsHorizontal_iP = intDx_iP != 0
            booIsCrossing_iP   = False

            if booIsHorizontal_iP:
                if intCellVal_iP in (6, 7):
                    continue
                if intCellVal_iP in (8, 9, 10, 11):
                    booIsCrossing_iP = True
            else:
                if intCellVal_iP in (8, 9):
                    continue
                if intCellVal_iP in (6, 7, 10, 11):
                    booIsCrossing_iP = True

            if booIsCrossing_iP:
                intNewCross_iP += 1
                if intNewCross_iP > intMaxCrossings_iA:
                    continue
                floMoveCost_iP += floCostCrossing_iA

            if intCellVal_iP in (6, 7, 8, 9, 10, 11):
                floMoveCost_iP += 2.0

            if intPrevDir_iP != -1 and intPrevDir_iP != intI_iP:
                floMoveCost_iP += floCostTurn_iA

            intDist_iP = arrDistMap_iA[intNy_iP][intNx_iP]
            if intDist_iP > 1:
                floMoveCost_iP += (intDist_iP - 1) * 2

            tupState_iP      = (intNx_iP, intNy_iP, intNewCross_iP)
            floTentativeG_iP = ditGScore_iL.get((intCx_iP, intCy_iP, intCCross_iP), float("inf")) + floMoveCost_iP

            if floTentativeG_iP < ditGScore_iL.get(tupState_iP, float("inf")):
                ditCameFrom_iL[tupState_iP] = (intCx_iP, intCy_iP, intCCross_iP)
                ditGScore_iL[tupState_iP]   = floTentativeG_iP
                floFScore_iP = floTentativeG_iP + fun_heuristic((intNx_iP, intNy_iP), tupEnd_iA)
                heapq.heappush(arrOpenSet_iL, (floFScore_iP, intNx_iP, intNy_iP, intNewCross_iP, intI_iP))

    return None


def FUN_GetNodeHeight_G(objNode_iA):
    if hasattr(objNode_iA, "dimensions") and objNode_iA.dimensions.y > 0:
        return objNode_iA.dimensions.y
    return max(100, max(len(objNode_iA.inputs), len(objNode_iA.outputs)) * 30 + 50)


def FUN_LayoutNodes_G(
    objTree_iA,
    intGridSize_iA,
    intStepX_iA,
    intStepY_iA,
    intPortSpacing_iA,
    intBarycenterPasses_iA,
    intMaxCrossings_iA,
    intMaxCrossingsFallback_iA,
    booAnimEnabled_iA,
    floAnimSpeed_iA,
    floCostTurn_iA,
    floCostCrossing_iA,
    floCostNearPort_iA,
    intNodeMargin_iA,
    intGridMargin_iA,
    booSimplifyPath_iA,
):
    global BOO_IsAnimating_dG

    if BOO_IsAnimating_dG:
        print("[ WARNING ] Router is already running!")
        return

    # --- 1. Убираем старые NodeReroute и восстанавливаем прямые связи ---
    print("[ 1 ] Restoring direct links, removing old reroutes...")
    arrResolvedLinks_iL = []
    for objNode_iP in objTree_iA.nodes:
        if objNode_iP.bl_idname == "NodeReroute":
            continue
        for objInp_iP in objNode_iP.inputs:
            for objLink_iP in objInp_iP.links:
                objFromSock_iP = FUN_ResolveFrom_G(objLink_iP.from_socket)
                if objFromSock_iP.node.bl_idname != "NodeReroute":
                    intFromIdx_iP = FUN_GetSocketIndex_G(objFromSock_iP.node, objFromSock_iP)
                    intToIdx_iP   = FUN_GetSocketIndex_G(objNode_iP, objInp_iP)
                    arrResolvedLinks_iL.append((
                        objFromSock_iP.node.name, intFromIdx_iP,
                        objNode_iP.name, intToIdx_iP
                    ))

    for objNode_iP in [n for n in objTree_iA.nodes if n.bl_idname == "NodeReroute"]:
        objTree_iA.nodes.remove(objNode_iP)

    for strFn_iP, intFs_iP, strTn_iP, intTs_iP in arrResolvedLinks_iL:
        objFromNode_iP = objTree_iA.nodes.get(strFn_iP)
        objToNode_iP   = objTree_iA.nodes.get(strTn_iP)
        if objFromNode_iP and objToNode_iP:
            objTree_iA.links.new(objFromNode_iP.outputs[intFs_iP], objToNode_iP.inputs[intTs_iP])

    # --- 2. Топологическая сортировка и начальная расстановка ---
    print("[ 2 ] Topological layout...")
    ditDepth_iL   = FUN_BuildTopoDepth_G(objTree_iA)
    ditColumns_iL = defaultdict(list)
    for objNode_iP in objTree_iA.nodes:
        if objNode_iP.bl_idname == "NodeReroute":
            continue
        ditColumns_iL[ditDepth_iL.get(objNode_iP.name, 0)].append(objNode_iP)

    intMaxDepth_iL  = max(ditColumns_iL.keys()) if ditColumns_iL else 0
    ditCurrentY_iL  = {}
    for intDepth_iP, arrNodes_iP in ditColumns_iL.items():
        floX_iP      = (intDepth_iP - intMaxDepth_iL) * intStepX_iA
        intCount_iP  = len(arrNodes_iP)
        floStartY_iP = ((intCount_iP - 1) * intStepY_iA) / 2
        for intIdx_iP, objNode_iP in enumerate(arrNodes_iP):
            floY_iP                        = floStartY_iP - intIdx_iP * intStepY_iA
            objNode_iP.location.x          = round(floX_iP / intGridSize_iA) * intGridSize_iA
            objNode_iP.location.y          = round(floY_iP / intGridSize_iA) * intGridSize_iA
            ditCurrentY_iL[objNode_iP.name] = objNode_iP.location.y

    # --- 3. Барицентрическое выравнивание ---
    print("[ 3 ] Barycenter passes...")
    for _ in range(intBarycenterPasses_iA):
        arrOrder_iP = sorted(ditColumns_iL.keys()) + sorted(ditColumns_iL.keys(), reverse=True)
        for intDepth_iP in arrOrder_iP:
            arrNodes_iP = ditColumns_iL[intDepth_iP]
            if len(arrNodes_iP) < 2:
                continue
            arrSorted_iP = sorted(
                arrNodes_iP,
                key=lambda n: FUN_GetAvgNeighborY_G(n, ditCurrentY_iL),
                reverse=True
            )
            intCount_iP  = len(arrSorted_iP)
            floStartY_iP = ((intCount_iP - 1) * intStepY_iA) / 2
            for intIdx_iP, objNode_iP in enumerate(arrSorted_iP):
                floY_iP                        = floStartY_iP - intIdx_iP * intStepY_iA
                objNode_iP.location.y          = round(floY_iP / intGridSize_iA) * intGridSize_iA
                ditCurrentY_iL[objNode_iP.name] = objNode_iP.location.y

    # Input/Output нодам — фиксированные позиции
    for objNode_iP in objTree_iA.nodes:
        if objNode_iP.bl_idname == "NodeGroupInput":
            objNode_iP.location.x = (0 - intMaxDepth_iL) * intStepX_iA - intStepX_iA
            objNode_iP.location.y = 0
        elif objNode_iP.bl_idname == "NodeGroupOutput":
            objNode_iP.location.x = intStepX_iA
            objNode_iP.location.y = 0

    # --- 4. Портовые рероуты ---
    print("[ 4 ] Creating port reroutes...")
    intPortSpacingGrid_iL = int(round(intPortSpacing_iA / intGridSize_iA))
    ditOutPorts_iL        = {}
    ditInPorts_iL         = {}

    for objNode_iP in objTree_iA.nodes:
        if objNode_iP.bl_idname == "NodeReroute":
            continue
        floH_iP      = FUN_GetNodeHeight_G(objNode_iP)
        floGyTop_iP  = int(round(objNode_iP.location.y / intGridSize_iA))
        floGyBot_iP  = int(round((objNode_iP.location.y - floH_iP) / intGridSize_iA))
        floCenterY_iP = (floGyTop_iP + floGyBot_iP) / 2.0

        arrLinkedOuts_iP = sorted(list(set(
            intFs for strFn, intFs, strTn, intTs in arrResolvedLinks_iL
            if strFn == objNode_iP.name
        )))
        arrLinkedIns_iP = sorted(list(set(
            intTs for strFn, intFs, strTn, intTs in arrResolvedLinks_iL
            if strTn == objNode_iP.name
        )))

        intNOut_iP       = len(arrLinkedOuts_iP)
        floStartOutY_iP  = floCenterY_iP + ((intNOut_iP - 1) * intPortSpacingGrid_iL) / 2.0
        for intI_iP, intFs_iP in enumerate(arrLinkedOuts_iP):
            objPort_iP            = objTree_iA.nodes.new("NodeReroute")
            objPort_iP.name       = f"PORT_OUT_{objNode_iP.name}_{intFs_iP}"
            objPort_iP.location.x = round((objNode_iP.location.x + objNode_iP.width + intPortSpacing_iA) / intGridSize_iA) * intGridSize_iA
            objPort_iP.location.y = round(floStartOutY_iP - intI_iP * intPortSpacingGrid_iL) * intGridSize_iA
            objTree_iA.links.new(objNode_iP.outputs[intFs_iP], objPort_iP.inputs[0])
            ditOutPorts_iL[(objNode_iP.name, intFs_iP)] = objPort_iP

        intNIn_iP       = len(arrLinkedIns_iP)
        floStartInY_iP  = floCenterY_iP + ((intNIn_iP - 1) * intPortSpacingGrid_iL) / 2.0
        for intI_iP, intTs_iP in enumerate(arrLinkedIns_iP):
            objPort_iP            = objTree_iA.nodes.new("NodeReroute")
            objPort_iP.name       = f"PORT_IN_{objNode_iP.name}_{intTs_iP}"
            objPort_iP.location.x = round((objNode_iP.location.x - intPortSpacing_iA) / intGridSize_iA) * intGridSize_iA
            objPort_iP.location.y = round(floStartInY_iP - intI_iP * intPortSpacingGrid_iL) * intGridSize_iA
            objTree_iA.links.new(objPort_iP.outputs[0], objNode_iP.inputs[intTs_iP])
            ditInPorts_iL[(objNode_iP.name, intTs_iP)] = objPort_iP

    # --- 5. Построение сетки ---
    print("[ 5 ] Building routing grid...")
    floMinX_iL, floMaxX_iL = float("inf"), float("-inf")
    floMinY_iL, floMaxY_iL = float("inf"), float("-inf")
    for objNode_iP in objTree_iA.nodes:
        floMinX_iL = min(floMinX_iL, objNode_iP.location.x - intPortSpacing_iA)
        floMaxX_iL = max(floMaxX_iL, objNode_iP.location.x + objNode_iP.width + intPortSpacing_iA)
        floH_iP    = FUN_GetNodeHeight_G(objNode_iP)
        floMinY_iL = min(floMinY_iL, objNode_iP.location.y - floH_iP - intPortSpacing_iA)
        floMaxY_iL = max(floMaxY_iL, objNode_iP.location.y + intPortSpacing_iA)

    intOffsetX_iL = int(round(floMinX_iL / intGridSize_iA)) - intGridMargin_iA
    intOffsetY_iL = int(round(floMinY_iL / intGridSize_iA)) - intGridMargin_iA
    intSizeX_iL   = int(round((floMaxX_iL - floMinX_iL) / intGridSize_iA)) + 2 * intGridMargin_iA
    intSizeY_iL   = int(round((floMaxY_iL - floMinY_iL) / intGridSize_iA)) + 2 * intGridMargin_iA

    arrGrid_iL = [[0] * intSizeX_iL for _ in range(intSizeY_iL)]

    for objNode_iP in objTree_iA.nodes:
        if objNode_iP.bl_idname == "NodeReroute":
            continue
        floW_iP      = objNode_iP.width
        floH_iP      = FUN_GetNodeHeight_G(objNode_iP)
        intGx1_iP    = int(round(objNode_iP.location.x / intGridSize_iA)) - intOffsetX_iL
        intGx2_iP    = int(round((objNode_iP.location.x + floW_iP) / intGridSize_iA)) - intOffsetX_iL
        intGyTop_iP  = int(round(objNode_iP.location.y / intGridSize_iA)) - intOffsetY_iL
        intGyBot_iP  = int(round((objNode_iP.location.y - floH_iP) / intGridSize_iA)) - intOffsetY_iL
        for intY_iP in range(max(0, intGyBot_iP - intNodeMargin_iA), min(intSizeY_iL, intGyTop_iP + 1 + intNodeMargin_iA)):
            for intX_iP in range(max(0, intGx1_iP - intNodeMargin_iA), min(intSizeX_iL, intGx2_iP + 1 + intNodeMargin_iA)):
                arrGrid_iL[intY_iP][intX_iP] = 1

    for tupKey_iP, objPort_iP in ditOutPorts_iL.items():
        intGx_iP = int(round(objPort_iP.location.x / intGridSize_iA)) - intOffsetX_iL
        intGy_iP = int(round(objPort_iP.location.y / intGridSize_iA)) - intOffsetY_iL
        if 0 <= intGy_iP < intSizeY_iL and 0 <= intGx_iP < intSizeX_iL:
            arrGrid_iL[intGy_iP][intGx_iP] = 3
            for intDy_iP in range(-1, 2):
                for intDx_iP in range(-1, 2):
                    if intDx_iP == 0 and intDy_iP == 0:
                        continue
                    intNx_iP, intNy_iP = intGx_iP + intDx_iP, intGy_iP + intDy_iP
                    if 0 <= intNy_iP < intSizeY_iL and 0 <= intNx_iP < intSizeX_iL and arrGrid_iL[intNy_iP][intNx_iP] == 0:
                        arrGrid_iL[intNy_iP][intNx_iP] = 5

    for tupKey_iP, objPort_iP in ditInPorts_iL.items():
        intGx_iP = int(round(objPort_iP.location.x / intGridSize_iA)) - intOffsetX_iL
        intGy_iP = int(round(objPort_iP.location.y / intGridSize_iA)) - intOffsetY_iL
        if 0 <= intGy_iP < intSizeY_iL and 0 <= intGx_iP < intSizeX_iL:
            arrGrid_iL[intGy_iP][intGx_iP] = 3
            for intDy_iP in range(-1, 2):
                for intDx_iP in range(-1, 2):
                    if intDx_iP == 0 and intDy_iP == 0:
                        continue
                    intNx_iP, intNy_iP = intGx_iP + intDx_iP, intGy_iP + intDy_iP
                    if 0 <= intNy_iP < intSizeY_iL and 0 <= intNx_iP < intSizeX_iL and arrGrid_iL[intNy_iP][intNx_iP] == 0:
                        arrGrid_iL[intNy_iP][intNx_iP] = 5

    arrDistMap_iL = [[100] * intSizeX_iL for _ in range(intSizeY_iL)]
    queQueue_iL   = deque()
    for intY_iP in range(intSizeY_iL):
        for intX_iP in range(intSizeX_iL):
            if arrGrid_iL[intY_iP][intX_iP] not in (0, 5):
                arrDistMap_iL[intY_iP][intX_iP] = 0
                queQueue_iL.append((intX_iP, intY_iP))

    while queQueue_iL:
        intX_iP, intY_iP = queQueue_iL.popleft()
        for intDx_iP, intDy_iP in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
            intNx_iP, intNy_iP = intX_iP + intDx_iP, intY_iP + intDy_iP
            if 0 <= intNx_iP < intSizeX_iL and 0 <= intNy_iP < intSizeY_iL:
                if arrDistMap_iL[intNy_iP][intNx_iP] > arrDistMap_iL[intY_iP][intX_iP] + 1:
                    arrDistMap_iL[intNy_iP][intNx_iP] = arrDistMap_iL[intY_iP][intX_iP] + 1
                    queQueue_iL.append((intNx_iP, intNy_iP))

    # --- 6. Прокладка коридоров (с анимацией или без) ---
    print("[ 6 ] Routing wires...")

    def fun_getLinkDist(tupItem_iA):
        (strFn_iP, intFs_iP), (strTn_iP, intTs_iP) = tupItem_iA
        objP1_iP = ditOutPorts_iL.get((strFn_iP, intFs_iP))
        objP2_iP = ditInPorts_iL.get((strTn_iP, intTs_iP))
        if not objP1_iP or not objP2_iP:
            return 0
        return abs(objP1_iP.location.x - objP2_iP.location.x) + abs(objP1_iP.location.y - objP2_iP.location.y)

    arrLinkKeys_iL = list(set(
        ((strFn, intFs), (strTn, intTs))
        for strFn, intFs, strTn, intTs in arrResolvedLinks_iL
    ))
    arrLinkKeys_iL.sort(key=fun_getLinkDist)

    def fun_yieldRedraw(floDelay_iA):
        objOldStdout_iP = sys.stdout
        sys.stdout = io.StringIO()
        try:
            bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=1)
        except Exception:
            pass
        finally:
            sys.stdout = objOldStdout_iP
        return floDelay_iA

    def fun_updateGrid(arrSimplifiedPath_iA, booIsHorizontalSegment_iA):
        """Обновляет сетку после прокладки одного провода"""
        for intI_iP in range(len(arrSimplifiedPath_iA) - 1):
            tupP1_iP     = arrSimplifiedPath_iA[intI_iP]
            tupP2_iP     = arrSimplifiedPath_iA[intI_iP + 1]
            booIsH_iP    = tupP1_iP[1] == tupP2_iP[1]
            intSteps_iP  = max(abs(tupP2_iP[0] - tupP1_iP[0]), abs(tupP2_iP[1] - tupP1_iP[1]))
            for intS_iP in range(intSteps_iP + 1):
                floT_iP  = intS_iP / max(intSteps_iP, 1)
                intIx_iP = int(round(tupP1_iP[0] + (tupP2_iP[0] - tupP1_iP[0]) * floT_iP))
                intIy_iP = int(round(tupP1_iP[1] + (tupP2_iP[1] - tupP1_iP[1]) * floT_iP))
                for intDy_iP in range(-1, 2):
                    for intDx_iP in range(-1, 2):
                        intNx_iP, intNy_iP = intIx_iP + intDx_iP, intIy_iP + intDy_iP
                        if not (0 <= intNy_iP < intSizeY_iL and 0 <= intNx_iP < intSizeX_iL):
                            continue
                        if arrGrid_iL[intNy_iP][intNx_iP] in (1, 3):
                            continue
                        if intDx_iP == 0 and intDy_iP == 0:
                            if booIsH_iP:
                                arrGrid_iL[intNy_iP][intNx_iP] = 10 if arrGrid_iL[intNy_iP][intNx_iP] in (8, 9, 10, 11) else 6
                            else:
                                arrGrid_iL[intNy_iP][intNx_iP] = 10 if arrGrid_iL[intNy_iP][intNx_iP] in (6, 7, 10, 11) else 8
                        else:
                            if booIsH_iP:
                                arrGrid_iL[intNy_iP][intNx_iP] = 11 if arrGrid_iL[intNy_iP][intNx_iP] in (8, 9, 10, 11) else 7
                            else:
                                arrGrid_iL[intNy_iP][intNx_iP] = 11 if arrGrid_iL[intNy_iP][intNx_iP] in (6, 7, 10, 11) else 9

    # --- Группировка fan-out: один out-порт → несколько in-портов одной ноды ---
    # Ключ: (strFn, intFs, strTn) → список intTs
    # Если группа > 1, прокладываем один провод до хаба, от хаба — ветки к каждому in-порту
    ditFanGroups_iL = defaultdict(list)
    for (strFn_iP, intFs_iP), (strTn_iP, intTs_iP) in arrLinkKeys_iL:
        ditFanGroups_iL[(strFn_iP, intFs_iP, strTn_iP)].append(intTs_iP)

    # Перестраиваем порядок обхода: сначала одиночные связи, затем fan-группы (чтобы хаб ставился после)
    # Для простоты — обрабатываем всё в порядке arrLinkKeys_iL,
    # но пропускаем дубликаты fan-группы после первой прокладки
    ditHubNodes_iL  = {}   # (strFn, intFs, strTn) → objHubReroute  (конечная точка магистрали)
    setRoutedFan_iL = set() # уже обработанные fan-группы

    def fun_routeSingleWire(objFrom_iA, objTo_iA):
        """Прокладывает A*-путь от objFrom_iA до objTo_iA.
        Возвращает генератор шагов (для yield) и финальный рероут-узел."""
        intStartGx_iP = int(round(objFrom_iA.location.x / intGridSize_iA)) - intOffsetX_iL
        intStartGy_iP = int(round(objFrom_iA.location.y / intGridSize_iA)) - intOffsetY_iL
        intEndGx_iP   = int(round(objTo_iA.location.x   / intGridSize_iA)) - intOffsetX_iL
        intEndGy_iP   = int(round(objTo_iA.location.y   / intGridSize_iA)) - intOffsetY_iL

        arrPath_iP = FUN_AStar_G(
            (intStartGx_iP, intStartGy_iP), (intEndGx_iP, intEndGy_iP),
            arrGrid_iL, arrDistMap_iL, intSizeX_iL, intSizeY_iL,
            intMaxCrossings_iA, floCostTurn_iA, floCostCrossing_iA, floCostNearPort_iA,
        )
        if not arrPath_iP:
            arrPath_iP = FUN_AStar_G(
                (intStartGx_iP, intStartGy_iP), (intEndGx_iP, intEndGy_iP),
                arrGrid_iL, arrDistMap_iL, intSizeX_iL, intSizeY_iL,
                intMaxCrossingsFallback_iA, floCostTurn_iA, floCostCrossing_iA, floCostNearPort_iA,
            )
        return arrPath_iP

    def clo_routingAnimation():
        global BOO_IsAnimating_dG
        try:
            for (strFn_iP, intFs_iP), (strTn_iP, intTs_iP) in arrLinkKeys_iL:
                objFromPort_iP = ditOutPorts_iL.get((strFn_iP, intFs_iP))
                objToPort_iP   = ditInPorts_iL.get((strTn_iP, intTs_iP))
                if not objFromPort_iP or not objToPort_iP:
                    continue

                strFanKey_iP   = (strFn_iP, intFs_iP, strTn_iP)
                arrFanGroup_iP = ditFanGroups_iL[strFanKey_iP]
                booIsFan_iP    = len(arrFanGroup_iP) > 1

                if booIsFan_iP:
                    if strFanKey_iP not in setRoutedFan_iL:
                        # --- Первый раз видим эту fan-группу ---
                        # Прокладываем магистраль от out-порта до среднего in-порта группы
                        # (берём первый в списке как цель магистрали, остальные — ветки от хаба)
                        intFirstTs_iP    = arrFanGroup_iP[0]
                        objFirstInPort_iP = ditInPorts_iL.get((strTn_iP, intFirstTs_iP))
                        if not objFirstInPort_iP:
                            continue

                        # Вычисляем среднюю Y позицию всех in-портов группы — туда ставим хаб
                        arrInPorts_iP = [
                            ditInPorts_iL.get((strTn_iP, intTs))
                            for intTs in arrFanGroup_iP
                            if ditInPorts_iL.get((strTn_iP, intTs))
                        ]
                        floHubX_iP = objFirstInPort_iP.location.x - intPortSpacing_iA
                        floHubY_iP = sum(p.location.y for p in arrInPorts_iP) / len(arrInPorts_iP)
                        floHubX_iP = round(floHubX_iP / intGridSize_iA) * intGridSize_iA
                        floHubY_iP = round(floHubY_iP / intGridSize_iA) * intGridSize_iA

                        # Создаём хаб-рероут
                        objHub_iP            = objTree_iA.nodes.new("NodeReroute")
                        objHub_iP.name       = "HUB"
                        objHub_iP.location.x = floHubX_iP
                        objHub_iP.location.y = floHubY_iP

                        if booAnimEnabled_iA:
                            yield fun_yieldRedraw(floAnimSpeed_iA)

                        # Прокладываем магистраль: out-порт → хаб
                        arrPath_iP = fun_routeSingleWire(objFromPort_iP, objHub_iP)
                        if arrPath_iP:
                            arrSimplified_iP = FUN_SimplifyPath_G(arrPath_iP) if booSimplifyPath_iA else arrPath_iP
                            objPrev_iP       = objFromPort_iP
                            for tupPxy_iP in arrSimplified_iP[1:-1]:
                                floWx_iP = (tupPxy_iP[0] + intOffsetX_iL) * intGridSize_iA
                                floWy_iP = (tupPxy_iP[1] + intOffsetY_iL) * intGridSize_iA
                                objRr_iP            = objTree_iA.nodes.new("NodeReroute")
                                objRr_iP.name       = "CORRIDOR"
                                objRr_iP.location.x = floWx_iP
                                objRr_iP.location.y = floWy_iP
                                objTree_iA.links.new(objPrev_iP.outputs[0], objRr_iP.inputs[0])
                                objPrev_iP = objRr_iP
                                if booAnimEnabled_iA:
                                    yield fun_yieldRedraw(floAnimSpeed_iA)
                            objTree_iA.links.new(objPrev_iP.outputs[0], objHub_iP.inputs[0])
                            if booAnimEnabled_iA:
                                yield fun_yieldRedraw(floAnimSpeed_iA)
                            fun_updateGrid(arrSimplified_iP, arrSimplified_iP[0][1] == arrSimplified_iP[1][1] if len(arrSimplified_iP) > 1 else True)
                        else:
                            # Путь до хаба не найден — просто подключаем напрямую
                            objTree_iA.links.new(objFromPort_iP.outputs[0], objHub_iP.inputs[0])

                        # Ветки: хаб → каждый in-порт группы (короткие прямые отрезки)
                        for intTs_iP2 in arrFanGroup_iP:
                            objBranchPort_iP = ditInPorts_iL.get((strTn_iP, intTs_iP2))
                            if not objBranchPort_iP:
                                continue
                            arrBranchPath_iP = fun_routeSingleWire(objHub_iP, objBranchPort_iP)
                            if arrBranchPath_iP:
                                arrBrSimpl_iP = FUN_SimplifyPath_G(arrBranchPath_iP) if booSimplifyPath_iA else arrBranchPath_iP
                                objPrev_iP    = objHub_iP
                                for tupPxy_iP in arrBrSimpl_iP[1:-1]:
                                    floWx_iP = (tupPxy_iP[0] + intOffsetX_iL) * intGridSize_iA
                                    floWy_iP = (tupPxy_iP[1] + intOffsetY_iL) * intGridSize_iA
                                    objRr_iP            = objTree_iA.nodes.new("NodeReroute")
                                    objRr_iP.name       = "CORRIDOR"
                                    objRr_iP.location.x = floWx_iP
                                    objRr_iP.location.y = floWy_iP
                                    objTree_iA.links.new(objPrev_iP.outputs[0], objRr_iP.inputs[0])
                                    objPrev_iP = objRr_iP
                                    if booAnimEnabled_iA:
                                        yield fun_yieldRedraw(floAnimSpeed_iA)
                                objTree_iA.links.new(objPrev_iP.outputs[0], objBranchPort_iP.inputs[0])
                                if booAnimEnabled_iA:
                                    yield fun_yieldRedraw(floAnimSpeed_iA)
                                fun_updateGrid(arrBrSimpl_iP, arrBrSimpl_iP[0][1] == arrBrSimpl_iP[1][1] if len(arrBrSimpl_iP) > 1 else True)
                            else:
                                objTree_iA.links.new(objHub_iP.outputs[0], objBranchPort_iP.inputs[0])

                        setRoutedFan_iL.add(strFanKey_iP)
                    # else: эта fan-группа уже полностью обработана, пропускаем

                else:
                    # --- Обычная одиночная связь ---
                    arrPath_iP = fun_routeSingleWire(objFromPort_iP, objToPort_iP)

                    if arrPath_iP:
                        arrSimplified_iP = FUN_SimplifyPath_G(arrPath_iP) if booSimplifyPath_iA else arrPath_iP
                        objPrevNode_iP   = objFromPort_iP

                        for tupPxy_iP in arrSimplified_iP[1:-1]:
                            floWx_iP = (tupPxy_iP[0] + intOffsetX_iL) * intGridSize_iA
                            floWy_iP = (tupPxy_iP[1] + intOffsetY_iL) * intGridSize_iA
                            objRr_iP            = objTree_iA.nodes.new("NodeReroute")
                            objRr_iP.name       = "CORRIDOR"
                            objRr_iP.location.x = floWx_iP
                            objRr_iP.location.y = floWy_iP
                            objTree_iA.links.new(objPrevNode_iP.outputs[0], objRr_iP.inputs[0])
                            objPrevNode_iP = objRr_iP
                            if booAnimEnabled_iA:
                                yield fun_yieldRedraw(floAnimSpeed_iA)

                        objTree_iA.links.new(objPrevNode_iP.outputs[0], objToPort_iP.inputs[0])
                        if booAnimEnabled_iA:
                            yield fun_yieldRedraw(floAnimSpeed_iA)
                        fun_updateGrid(arrSimplified_iP, arrSimplified_iP[0][1] == arrSimplified_iP[1][1] if len(arrSimplified_iP) > 1 else True)

                    else:
                        print(f"[ ERROR ] No path: {strFn_iP}({intFs_iP}) -> {strTn_iP}({intTs_iP})")

            BOO_IsAnimating_dG = False
            print(f"[ OK ] Routing complete: '{objTree_iA.name}'")

        except Exception as objErr_iP:
            BOO_IsAnimating_dG = False
            print(f"[ ERROR ] {objErr_iP}")

    BOO_IsAnimating_dG = True

    if booAnimEnabled_iA:
        objGen_iL = clo_routingAnimation()

        def fun_timerStep():
            try:
                return next(objGen_iL)
            except StopIteration:
                return None

        bpy.app.timers.register(fun_timerStep)
    else:
        # Без анимации — запускаем генератор до конца сразу
        objGen_iL = clo_routingAnimation()
        for _ in objGen_iL:
            pass

# ! КОНЕЦ БЛОКА ФУНКЦИИ


# ! НАЧАЛО БЛОКА РЕГИСТРАЦИЯ

ARR_Classes_cF = [
    CLS_NodeRouterProps_G,
    CLS_NodeRouterPanel_G,
    CLS_RunRouterOp_G,
]

def register():
    for objCls_iP in ARR_Classes_cF:
        bpy.utils.register_class(objCls_iP)
    bpy.types.Scene.nodeRouterProps = bpy.props.PointerProperty(type=CLS_NodeRouterProps_G)
    print("[ Node Dungeon Router ] Registered.")

def unregister():
    for objCls_iP in reversed(ARR_Classes_cF):
        bpy.utils.unregister_class(objCls_iP)
    del bpy.types.Scene.nodeRouterProps
    print("[ Node Dungeon Router ] Unregistered.")

if __name__ == "__main__":
    register()

# ! КОНЕЦ БЛОКА РЕГИСТРАЦИЯ
