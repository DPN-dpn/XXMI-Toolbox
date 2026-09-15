import bpy

def separate_by_vertex_group_clusters(context, obj):
    """
    버텍스 그룹과 물리적 연결성(Edge)을 바탕으로 메쉬를 클러스터(덩어리)로 묶어 분리합니다.
    - 대상 메쉬의 이름으로 새 컬렉션을 만들고 그 안에서 작업이 진행됩니다.
    - 물리적으로 연결되어 있거나 (Edge 공유)
    - 하나의 버텍스에 여러 그룹이 할당되어 있으면
    해당 버텍스 그룹들은 하나의 클러스터로 병합됩니다.
    """
    if not obj or obj.type != 'MESH':
        return False, "타겟 메쉬 오브젝트가 지정되지 않았거나 메쉬가 아닙니다."
        
    if len(obj.vertex_groups) == 0:
        return False, "오브젝트에 버텍스 그룹이 존재하지 않습니다."

    print(f"\n[메쉬 분리 시작] 대상 오브젝트: '{obj.name}'")

    # 작업은 항상 오브젝트 모드에서 시작
    if context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    # 오브젝트 자체의 숨김 및 선택 불가 상태 해제
    if obj.hide_get():
        obj.hide_set(False)
    if obj.hide_select:
        obj.hide_select = False

    # 1. 대상 오브젝트 이름으로 새 컬렉션 생성
    new_col_name = obj.name
    new_col = bpy.data.collections.new(new_col_name)
    
    # 부모 컬렉션이 뷰포트에서 숨겨져(가려져) 있을 경우 에러가 발생하는 것을 방지하기 위해,
    # 작업 중에는 무조건 씬(Scene) 최상단에 임시로 링크해 둡니다.
    context.scene.collection.children.link(new_col)
    
    # 원본 오브젝트가 속해 있던 컬렉션들 기록
    old_collections = obj.users_collection[:]
    
    # 원본 오브젝트를 새 컬렉션으로 이동 (기존 컬렉션에서는 제외)
    new_col.objects.link(obj)
    for col in old_collections:
        col.objects.unlink(obj)
        
    print(f"  - 임시 씬 최상단에 새 컬렉션 '{new_col_name}' 생성 및 이동 완료.")

    # 2. Union-Find 초기화 (버텍스 그룹 간의 병합 추적용)
    parent = {}
    def find(i):
        if i not in parent: parent[i] = i
        if parent[i] == i: return i
        parent[i] = find(parent[i])
        return parent[i]

    def union(i, j):
        root_i, root_j = find(i), find(j)
        if root_i != root_j:
            parent[root_i] = root_j

    # 3. 버텍스 그룹 및 엣지 연결성 기반으로 그룹 병합(Union)
    # 3-1. 하나의 버텍스에 여러 그룹이 겹쳐있으면 병합
    v_groups = {}
    for v in obj.data.vertices:
        groups = [g.group for g in v.groups]
        v_groups[v.index] = groups
        if len(groups) > 1:
            first_g = groups[0]
            for g in groups[1:]:
                union(first_g, g)

    # 3-2. 엣지로 연결된 두 버텍스의 그룹들도 병합 (물리적 연결)
    for edge in obj.data.edges:
        groups1 = v_groups[edge.vertices[0]]
        groups2 = v_groups[edge.vertices[1]]
        for g1 in groups1:
            for g2 in groups2:
                union(g1, g2)

    # 4. 각 버텍스를 최종 클러스터(루트 그룹) 별로 분류
    cluster_verts = {}
    for v_idx, groups in v_groups.items():
        if groups: # 버텍스 그룹이 있는 정점만 처리
            root = find(groups[0])
            if root not in cluster_verts:
                cluster_verts[root] = []
            cluster_verts[root].append(v_idx)

    if not cluster_verts:
        return False, "버텍스 그룹에 할당된 정점이 하나도 없습니다."

    print(f"  - 총 {len(cluster_verts)}개의 버텍스 그룹 클러스터 식별됨.")

    # 5. 각 클러스터에 속한 원래 그룹 이름들 수집
    vg_names = {vg.index: vg.name for vg in obj.vertex_groups}
    cluster_group_names = {}
    for idx, name in vg_names.items():
        root = find(idx)
        if root not in cluster_group_names:
            cluster_group_names[root] = set()
        cluster_group_names[root].add(name)

    # 6. 임시 버텍스 그룹(선택용) 생성 및 최종 오브젝트 이름 맵핑
    target_names_map = {}
    for root, v_indices in cluster_verts.items():
        tg_name = f"__temp_split_{root}__"
        temp_vg = obj.vertex_groups.new(name=tg_name)
        temp_vg.add(v_indices, 1.0, 'REPLACE')
        
        # 이름 규칙: 새 컬렉션 내부이므로 접두사 없이 그룹 이름만 사용
        if root in cluster_group_names:
            merged_names = " ".join(sorted(list(cluster_group_names[root])))
            target_names_map[tg_name] = merged_names
        else:
            target_names_map[tg_name] = f"Cluster_{root}"

    # 7. 실제 메쉬 분리 작업 (Separate by Selected)
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    context.view_layer.objects.active = obj
    
    separated_objects = []

    for tg_name, target_name in target_names_map.items():
        existing_objs = set(context.scene.objects)
        
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='DESELECT')
        
        # 임시 그룹에 속한 버텍스들 선택
        bpy.ops.object.vertex_group_set_active(group=tg_name)
        bpy.ops.object.vertex_group_select()
        
        try:
            # 선택된 버텍스를 별도 오브젝트로 분리
            bpy.ops.mesh.separate(type='SELECTED')
        except RuntimeError:
            # 선택된 정점이 없거나 분리할 수 없는 경우 무시
            bpy.ops.object.mode_set(mode='OBJECT')
            continue
            
        bpy.ops.object.mode_set(mode='OBJECT')
        
        # 새로 생성된 오브젝트 찾아서 이름 변경
        new_objs = set(context.scene.objects) - existing_objs
        if new_objs:
            new_obj = list(new_objs)[0]
            new_obj.name = target_name
            separated_objects.append(new_obj)
            print(f"  - 분리 완료: '{target_name}' (정점 수: {len(new_obj.data.vertices)})")
            
        # 다음 작업을 위해 원래 오브젝트 다시 활성화
        bpy.ops.object.select_all(action='DESELECT')
        context.view_layer.objects.active = obj
        obj.select_set(True)

    # 8. 찌꺼기 청소: 모든 오브젝트에서 임시로 만들었던 버텍스 그룹 삭제
    all_objs_to_clean = [obj] + separated_objects
    for clean_obj in all_objs_to_clean:
        for tg_name in target_names_map.keys():
            vg = clean_obj.vertex_groups.get(tg_name)
            if vg:
                clean_obj.vertex_groups.remove(vg)

    # 9. 남은 원본 오브젝트 처리 (버텍스 0개면 삭제, 남았으면 미할당 정점으로 이름 변경)
    leftover_verts_count = len(obj.data.vertices)
    if leftover_verts_count == 0:
        print("  - 모든 정점이 분리되어 원본 빈 껍데기 오브젝트를 삭제합니다.")
        bpy.data.objects.remove(obj, do_unlink=True)
        leftover_msg = " (미할당 정점 없음)"
    else:
        obj.name = "Unassigned_Vertices"
        print(f"  - 할당되지 않은 정점이 {leftover_verts_count}개 발견되어 '{obj.name}'으로 보존합니다.")
        leftover_msg = f" (미할당 정점 {leftover_verts_count}개 발견됨)"

    # 10. 분리 작업이 모두 끝난 후, 새 컬렉션을 원래 속해있던 부모 컬렉션 아래로 다시 이동 (숨김 에러 회피용)
    if old_collections:
        parent_col = old_collections[0]
        context.scene.collection.children.unlink(new_col)
        parent_col.children.link(new_col)
        print(f"  - 새 컬렉션 '{new_col_name}'을 부모 컬렉션 '{parent_col.name}' 아래로 이동 복구했습니다.")

    print(f"[메쉬 분리 완료] 총 {len(separated_objects)}개의 파츠로 성공적으로 쪼개졌습니다.\n")
    return True, f"총 {len(separated_objects)}개의 파츠로 분리 완료!{leftover_msg}"

class XXMI_OT_separate_mesh(bpy.types.Operator):
    bl_idname = "object.xxmi_separate_mesh"
    bl_label = "버텍스 그룹 기준 메쉬 분리"
    bl_description = "버텍스 그룹을 기반으로 오브젝트를 쪼갭니다"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        props = context.scene.xxmi_separate_mesh_props
        return props.target_obj is not None and props.target_obj.type == 'MESH'

    def execute(self, context):
        props = context.scene.xxmi_separate_mesh_props
        
        if not props.target_obj:
            self.report({'ERROR'}, "분리할 대상(타겟) 메쉬를 지정해주세요!")
            return {'CANCELLED'}

        success, message = separate_by_vertex_group_clusters(context, props.target_obj)
        if success:
            self.report({'INFO'}, message)
        else:
            self.report({'ERROR'}, message)
        return {'FINISHED'}

classes = (
    XXMI_OT_separate_mesh,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
