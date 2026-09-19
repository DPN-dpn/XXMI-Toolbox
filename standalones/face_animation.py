import bpy
import struct
import os
import re
import json
import math
import traceback
from mathutils import Vector
from mathutils.bvhtree import BVHTree

# ======================================================================
# [사용 방법]
# 1. 블렌더의 'Scripting' 워크스페이스에서 이 스크립트를 엽니다.
# 2. 아래 [사용자 설정] 섹션의 경로(DUMP_HASH_JSON, TARGET_INI)와 
#    변수들을 본인의 파일 경로에 맞게 직접 수정합니다.
# 3. (선택) 형태를 맞춘 원본 얼굴 오브젝트를 보간 기준으로 사용하려면, 
#    해당 오브젝트를 선택(Active)한 상태로 둡니다. (선택 안하면 기본 좌표계 사용)
# 4. 상단의 'Run Script (▶)' 버튼을 눌러 실행합니다.
# ======================================================================

# ======================================================================
# [ 설정 ]
# ======================================================================
DUMP_HASH_JSON = r"C:\path\to\your\dump\hash.json"
TARGET_INI     = r"C:\path\to\your\mod\mod.ini"

# hash.json에서의 얼굴 컴포넌트 이름
SELECTED_COMPONENT = "Face"

# 맵핑 방식 (아래 옵션 중 하나를 선택하세요)
# - 'TOPOLOGY': 동일한 버텍스 인덱스를 1:1로 매칭합니다
# - 'NEAREST_VERTEX': 가장 가까운 1개의 점에 100% 매핑합니다
# - 'NEAREST_FACE_VERTEX': 가장 가까운 면의 점 중 하나에 매핑합니다
# - 'NEAREST_FACE_INTERPOLATED': (추천) 가장 가까운 면의 3개 점에 무게중심으로 가중치를 분배합니다
# - 'PROJECTED_FACE_INTERPOLATED': 법선 방향으로 레이저를 쏴 부딪힌 면을 기준으로 보간합니다
MAPPING_METHOD = "NEAREST_FACE_INTERPOLATED"

# ======================================================================
# [ 로직 ]
# ======================================================================

def show_message_box(message, title="에러", icon='ERROR'):
    def draw(self, context):
        self.layout.label(text=message)
    bpy.context.window_manager.popup_menu(draw, title=title, icon=icon)
    print(f"[{title}] {message}")

def find_file_with_hash(folder, hash_val, keyword):
    for f in os.listdir(folder):
        if keyword in f and hash_val in f and f.endswith(".txt"):
            return os.path.join(folder, f)
    return None

def parse_and_get_custom_buf(ini_path, blend_hash):
    with open(ini_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    in_target_section = False
    resource_key = None
    custom_buf_name = None
    
    for line in lines:
        l = line.strip().lower()
        if l.startswith('[') and l.endswith(']'):
            in_target_section = False
            
        if l == f"hash = {blend_hash.lower()}":
            in_target_section = True
            
        if in_target_section:
            if l.startswith("vb0 ") or l.startswith("vb0="):
                parts = l.split("=", 1)
                if len(parts) == 2:
                    res_val = parts[1].strip()
                    if res_val.lower() != "resourcefaceanimated":
                        resource_key = res_val
                        
        if l.startswith("cs-u5") and "copy" in l:
            parts = l.split("copy", 1)
            if len(parts) == 2:
                potential_key = parts[1].strip()
                if potential_key.lower() != "resourcefaceexpressionbase": 
                    if not resource_key:
                        resource_key = potential_key
                else:
                    if not resource_key:
                        resource_key = potential_key
                        
    if not resource_key:
        return None, lines
        
    in_res_section = False
    for line in lines:
        l = line.strip()
        if l.startswith('[') and l.endswith(']'):
            in_res_section = (l[1:-1].strip().lower() == resource_key.lower())
            
        if in_res_section and l.lower().startswith("filename"):
            parts = l.split("=", 1)
            if len(parts) == 2:
                custom_buf_name = parts[1].strip()
                break
                
    return custom_buf_name, lines

def parse_dump_txt(vb0_path, ib_path, out_buf_path):
    vertices = []
    buf_data = bytearray()
    vertex_count = 0
    
    with open(vb0_path, 'r', encoding='utf-8') as f:
        current_pos = [0.0, 0.0, 0.0]
        current_norm = [0.0, 0.0, 0.0]
        current_tang = [0.0, 0.0, 0.0, 0.0]
        
        for line in f:
            l = line.strip()
            if l.startswith("vertex count:"):
                vertex_count = int(l.split(":")[1].strip())
                
            if "POSITION:" in l:
                vals = l.split("POSITION:")[1].strip().split(",")
                current_pos = [float(v.strip()) for v in vals]
                vertices.append(Vector(current_pos))
                
            elif "NORMAL:" in l:
                vals = l.split("NORMAL:")[1].strip().split(",")
                current_norm = [float(v.strip()) for v in vals]
                
            elif "TANGENT:" in l:
                vals = l.split("TANGENT:")[1].strip().split(",")
                current_tang = [float(v.strip()) for v in vals]
                buf_data.extend(struct.pack('<3f', *current_pos))
                buf_data.extend(struct.pack('<3f', *current_norm))
                buf_data.extend(struct.pack('<4f', *current_tang))
                
    with open(out_buf_path, 'wb') as f:
        f.write(buf_data)
        
    polygons = []
    with open(ib_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        for line in lines:
            l = line.strip()
            if not l or l.startswith("byte") or l.startswith("first") or l.startswith("index") or l.startswith("topology") or l.startswith("format"):
                continue
            parts = l.split()
            if len(parts) >= 3:
                polygons.append((int(parts[0]), int(parts[1]), int(parts[2])))
                
    return vertices, polygons, vertex_count

def build_animation_map(custom_buf_path, bvh, orig_vertices, orig_polygons, out_map_path, mapping_method):
    from mathutils.geometry import barycentric_transform
    
    custom_vertex_count = 0
    map_data = bytearray()
    
    with open(custom_buf_path, 'rb') as f:
        while True:
            pos_bytes = f.read(12)
            if not pos_bytes or len(pos_bytes) < 12:
                break
            norm_bytes = f.read(12)
            f.read(16) 
            
            custom_vertex_count += 1
            pos = struct.unpack('<3f', pos_bytes)
            v_pos = Vector(pos)
            norm = struct.unpack('<3f', norm_bytes)
            v_norm = Vector(norm)
            if v_norm.length > 0:
                v_norm.normalize()
            
            if mapping_method == 'TOPOLOGY':
                idx = min(custom_vertex_count - 1, len(orig_vertices) - 1)
                struct_data = struct.pack('<3I 3I 3f 3f', idx, 0, 0, 0, 0, 0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0)
                map_data.extend(struct_data)
                continue
                
            if mapping_method == 'NEAREST_VERTEX':
                location, normal, index, distance = bvh.find_nearest(v_pos)
                if location is None:
                    struct_data = struct.pack('<3I 3I 3f 3f', 0,0,0, 0,0,0, 1.0,0.0,0.0, 0.0,0.0,0.0)
                else:
                    poly = orig_polygons[index]
                    dists = [ (v_pos - orig_vertices[i]).length for i in poly ]
                    min_i = poly[dists.index(min(dists))]
                    struct_data = struct.pack('<3I 3I 3f 3f', min_i, 0, 0, 0, 0, 0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0)
                map_data.extend(struct_data)
                continue
                
            location = None
            index = -1
            
            if mapping_method == 'PROJECTED_FACE_INTERPOLATED':
                location, normal, index, distance = bvh.ray_cast(v_pos - v_norm * 0.1, v_norm)
                if location is None:
                    location, normal, index, distance = bvh.ray_cast(v_pos + v_norm * 0.1, -v_norm)
                    
            if location is None:
                location, normal, index, distance = bvh.find_nearest(v_pos)
                
            if location is None:
                struct_data = struct.pack('<3I 3I 3f 3f', 0,0,0, 0,0,0, 1.0,0.0,0.0, 0.0,0.0,0.0)
                map_data.extend(struct_data)
                continue
                
            poly = orig_polygons[index]
            
            if mapping_method == 'NEAREST_FACE_VERTEX':
                dists = [ (location - orig_vertices[i]).length for i in poly ]
                min_i = poly[dists.index(min(dists))]
                struct_data = struct.pack('<3I 3I 3f 3f', min_i, 0, 0, 0, 0, 0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0)
            else:
                p1 = orig_vertices[poly[0]]
                p2 = orig_vertices[poly[1]]
                p3 = orig_vertices[poly[2]]
                
                try:
                    weights = barycentric_transform(location, p1, p2, p3, Vector((1,0,0)), Vector((0,1,0)), Vector((0,0,1)))
                    w0, w1, w2 = weights.x, weights.y, weights.z
                except Exception:
                    w0, w1, w2 = 1.0, 0.0, 0.0
                    
                struct_data = struct.pack('<3I 3I 3f 3f', poly[0], poly[1], poly[2], 0, 0, 0, w0, w1, w2, 0.0, 0.0, 0.0)
                
            map_data.extend(struct_data)
            
    with open(out_map_path, 'wb') as f:
        f.write(map_data)
        
    return custom_vertex_count

def export_hlsl(directory, custom_vtx_count, orig_vtx_count):
    hlsl_code = f"""// Transfer live pre-skinning facial deformation to the custom face.
struct Vertex {{
    float3 position;
    float3 normal;
    float4 tangent;
}};
struct Attachment {{
    uint3 first;
    uint3 second;
    float3 firstWeights;
    float3 secondWeights;
}};

StructuredBuffer<Vertex> Live : register(t50);
StructuredBuffer<Vertex> Neutral : register(t51);
StructuredBuffer<Attachment> Map : register(t52);
RWStructuredBuffer<Vertex> Output : register(u5);

float blinkAmount(uint probe) {{
    return 0.0;
}}

float3 residual(uint index, float2 blink) {{
    return Live[index].position - Neutral[index].position;
}}

[numthreads(64, 1, 1)]
void main(uint3 threadID : SV_DispatchThreadID) {{
    uint i = threadID.x;
    if (i >= {custom_vtx_count}) return;
    uint sourceCount, sourceStride;
    Live.GetDimensions(sourceCount, sourceStride);
    if (sourceCount != {orig_vtx_count} || sourceStride != 40) return;
    Attachment a = Map[i];
    float3 delta = 0;
    [unroll] for (uint j = 0; j < 3; ++j) {{
        if (a.firstWeights[j] != 0)
            delta += residual(a.first[j], float2(0,0)) * a.firstWeights[j];
        if (a.secondWeights[j] != 0)
            delta += residual(a.second[j], float2(0,0)) * a.secondWeights[j];
    }}
    
    Vertex vertex = Output[i];
    vertex.position += delta;
    Output[i] = vertex;
}}
"""
    with open(os.path.join(directory, "FaceAnimation.hlsl"), 'w', encoding='utf-8') as f:
        f.write(hlsl_code)

def inject_ini(ini_path, lines, custom_buf_name, blend_hash):
    has_custom_shader = False
    for l in lines:
        if "[CustomShaderFaceAnimation]" in l:
            has_custom_shader = True
            break
            
    out_lines = []
    in_target_section = False
    in_draw_type_1 = False
    
    for i, line in enumerate(lines):
        l = line.strip().lower()
        if l.startswith('[') and l.endswith(']'):
            in_target_section = False
            in_draw_type_1 = False
            
        if l == f"hash = {blend_hash.lower()}":
            in_target_section = True
            
        if in_target_section:
            if "if draw_type" in l and "1" in l:
                in_draw_type_1 = True
            elif "endif" in l or "elif" in l:
                if in_draw_type_1:
                    in_draw_type_1 = False
                    
            if in_draw_type_1:
                if l.startswith("vb0 ") or l.startswith("vb0="):
                    if "resourcefaceanimated" not in l:
                        indent = line[:len(line) - len(line.lstrip())]
                        out_lines.append(f"{indent}run = CustomShaderFaceAnimation\n")
                        out_lines.append(f"{indent}vb0 = ResourceFaceAnimated\n")
                        continue 
                if l.startswith("run ") and "customshaderfaceanimation" in l:
                    continue
                    
        out_lines.append(line)
        
    if not has_custom_shader:
        custom_size = os.path.getsize(os.path.join(os.path.dirname(ini_path), custom_buf_name))
        v_count = custom_size // 40
        dispatch_groups = math.ceil(v_count / 64.0)
        
        appended_ini = f"""

; ==========================================================
; XXMI Face Animation Auto-Injected
; ==========================================================
[CustomShaderFaceAnimation]
cs = FaceAnimation.hlsl
ResourceFaceLive = copy vb0
cs-t50 = ref ResourceFaceLive
cs-t51 = ref ResourceFaceOriginalNeutral
cs-t52 = ref ResourceFaceAnimationMap
cs-u5 = copy ResourceCustomFaceExtracted
ResourceFaceAnimated = ref cs-u5
Dispatch = {dispatch_groups}, 1, 1
cs-u5 = null
cs-t50 = null
cs-t51 = null
cs-t52 = null

[ResourceFaceLive]
type = StructuredBuffer
stride = 40

[ResourceFaceAnimated]

[ResourceFaceOriginalNeutral]
type = StructuredBuffer
stride = 40
filename = FaceOriginalNeutral.buf

[ResourceFaceAnimationMap]
type = StructuredBuffer
stride = 48
filename = FaceAnimationMap.buf

[ResourceCustomFaceExtracted]
type = StructuredBuffer
stride = 40
filename = {custom_buf_name}
; ==========================================================
"""
        out_lines.append(appended_ini)
        
    with open(ini_path, 'w', encoding='utf-8') as f:
        f.writelines(out_lines)

def main():
    if not os.path.isfile(DUMP_HASH_JSON):
        show_message_box("에셋 hash.json 파일을 올바르게 지정해주세요.")
        return
        
    dump_folder = os.path.dirname(DUMP_HASH_JSON)
    
    if not os.path.isfile(TARGET_INI):
        show_message_box("타겟 모드 ini 파일을 올바르게 지정해주세요.")
        return
        
    try:
        with open(DUMP_HASH_JSON, 'r', encoding='utf-8') as f:
            hash_data = json.load(f)
            
        comp_data = next((c for c in hash_data if c.get("component_name") == SELECTED_COMPONENT), None)
        if not comp_data:
            show_message_box(f"hash.json에서 {SELECTED_COMPONENT} 컴포넌트를 찾을 수 없습니다.")
            return
            
        pos_vb_hash = comp_data.get("position_vb")
        ib_hash = comp_data.get("ib")
        blend_vb_hash = comp_data.get("blend_vb")
        
        if not pos_vb_hash or not ib_hash:
            show_message_box("컴포넌트에 필요한 해시(position_vb, ib)가 부족합니다.")
            return
            
        vb0_txt = find_file_with_hash(dump_folder, pos_vb_hash, "-vb0=")
        ib_txt = find_file_with_hash(dump_folder, ib_hash, "-ib=")
        
        if not vb0_txt or not ib_txt:
            show_message_box(f"에셋 폴더에서 {SELECTED_COMPONENT}의 -vb0 또는 -ib 텍스트 파일을 찾을 수 없습니다.")
            return
            
        custom_buf_name, ini_lines = parse_and_get_custom_buf(TARGET_INI, blend_vb_hash)
        if not custom_buf_name:
            show_message_box("ini 파일에서 커스텀 얼굴 버퍼를 추적할 수 없습니다.")
            return
            
        mod_folder = os.path.dirname(TARGET_INI)
        custom_buf_path = os.path.join(mod_folder, custom_buf_name)
        if not os.path.isfile(custom_buf_path):
            show_message_box(f"커스텀 버퍼 파일이 존재하지 않습니다: {custom_buf_name}")
            return
            
        orig_vertices, orig_polygons, orig_vertex_count = parse_dump_txt(vb0_txt, ib_txt, os.path.join(mod_folder, "FaceOriginalNeutral.buf"))
        
        bvh_vertices = orig_vertices
        
        # 스탠드얼론: 활성화된 오브젝트가 선택되어 있으면 형태 맞춤으로 사용
        active_obj = bpy.context.active_object
        if active_obj and active_obj.type == 'MESH':
            mesh = active_obj.data
            if len(mesh.vertices) == orig_vertex_count:
                print("선택된 메쉬를 형태 맞춤 기준으로 적용합니다.")
                bvh_vertices = [v.co for v in mesh.vertices]
            else:
                print(f"(경고) 선택된 메쉬의 버텍스 개수({len(mesh.vertices)})가 원본({orig_vertex_count})과 달라 무시됩니다.")
                
        bvh = BVHTree.FromPolygons(bvh_vertices, orig_polygons)
        
        custom_vertex_count = build_animation_map(custom_buf_path, bvh, bvh_vertices, orig_polygons, os.path.join(mod_folder, "FaceAnimationMap.buf"), MAPPING_METHOD)
        
        export_hlsl(mod_folder, custom_vertex_count, orig_vertex_count)
        
        inject_ini(TARGET_INI, ini_lines, custom_buf_name, blend_hash)
        
        show_message_box("모드 폴더에 버퍼와 쉐이더가 성공적으로 생성 및 적용되었습니다.", title="표정 연동 완료", icon='INFO')
        
    except Exception as e:
        traceback.print_exc()
        show_message_box(f"에러 발생: {str(e)}")

if __name__ == "__main__":
    main()
