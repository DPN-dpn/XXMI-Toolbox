import sys
import struct
import os
import json
import math
import traceback
import argparse
import re

# ======================================================================
# [사용 방법]
# - 인자 없이 실행: python face_animation.py
#   → 대화형 메뉴로 진행 (1: 표정 연동 적용, 2: 롤백)
#
# - 인자로 직접 실행:
#   python face_animation.py --hash <dump폴더> --ini <mod폴더> [옵션]
#   python face_animation.py --rollback --ini <mod폴더>
#
# - 도움말: python face_animation.py --help
# ======================================================================

# ======================================================================
# [ 수학 및 기하학 유틸리티 (Pure Python, 외부 라이브러리 불필요) ]
# ======================================================================
def v_sub(a, b): return (a[0]-b[0], a[1]-b[1], a[2]-b[2])
def v_dot(a, b): return a[0]*b[0] + a[1]*b[1] + a[2]*b[2]
def v_add(a, b): return (a[0]+b[0], a[1]+b[1], a[2]+b[2])
def v_mul(a, s): return (a[0]*s, a[1]*s, a[2]*s)
def v_dist_sq(a, b): return (a[0]-b[0])**2 + (a[1]-b[1])**2 + (a[2]-b[2])**2

def barycentric_weights(p, a, b, c):
    v0, v1, v2 = v_sub(b, a), v_sub(c, a), v_sub(p, a)
    d00, d01, d11 = v_dot(v0, v0), v_dot(v0, v1), v_dot(v1, v1)
    d20, d21 = v_dot(v2, v0), v_dot(v2, v1)
    denom = d00 * d11 - d01 * d01
    if denom == 0: return 1.0, 0.0, 0.0
    v = (d11 * d20 - d01 * d21) / denom
    w = (d00 * d21 - d01 * d20) / denom
    return 1.0 - v - w, v, w

def point_triangle_distance_sq(p, a, b, c):
    ab, ac, ap = v_sub(b, a), v_sub(c, a), v_sub(p, a)
    d1, d2 = v_dot(ab, ap), v_dot(ac, ap)
    if d1 <= 0.0 and d2 <= 0.0: return v_dot(ap, ap)
    bp = v_sub(p, b)
    d3, d4 = v_dot(ab, bp), v_dot(ac, bp)
    if d3 >= 0.0 and d4 <= d3: return v_dot(bp, bp)
    vc = d1*d4 - d3*d2
    if vc <= 0.0 and d1 >= 0.0 and d3 <= 0.0:
        v = d1 / (d1 - d3)
        proj = v_add(a, v_mul(ab, v))
        return v_dot(v_sub(p, proj), v_sub(p, proj))
    cp = v_sub(p, c)
    d5, d6 = v_dot(ab, cp), v_dot(ac, cp)
    if d6 >= 0.0 and d5 <= d6: return v_dot(cp, cp)
    vb = d5*d2 - d1*d6
    if vb <= 0.0 and d2 >= 0.0 and d6 <= 0.0:
        w = d2 / (d2 - d6)
        proj = v_add(a, v_mul(ac, w))
        return v_dot(v_sub(p, proj), v_sub(p, proj))
    va = d3*d6 - d5*d4
    if va <= 0.0 and (d4 - d3) >= 0.0 and (d5 - d6) >= 0.0:
        w = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        proj = v_add(b, v_mul(v_sub(c, b), w))
        return v_dot(v_sub(p, proj), v_sub(p, proj))
    denom = 1.0 / (va + vb + vc)
    v, w = vb * denom, vc * denom
    proj = v_add(a, v_add(v_mul(ab, v), v_mul(ac, w)))
    return v_dot(v_sub(p, proj), v_sub(p, proj))

# KD-Tree: 대량의 3D 점에서 가장 가까운 점을 빠르게 찾기 위한 자료구조
class KDNode:
    __slots__ = ['point', 'index', 'left', 'right']
    def __init__(self, point, index, left, right):
        self.point = point
        self.index = index
        self.left = left
        self.right = right

def build_kdtree(points_with_indices, depth=0):
    if not points_with_indices:
        return None
    axis = depth % 3
    points_with_indices.sort(key=lambda x: x[0][axis])
    mid = len(points_with_indices) // 2
    return KDNode(
        points_with_indices[mid][0], points_with_indices[mid][1],
        build_kdtree(points_with_indices[:mid], depth + 1),
        build_kdtree(points_with_indices[mid + 1:], depth + 1)
    )

def kdtree_k_nearest(node, target, k=10, depth=0, best_list=None):
    if best_list is None: best_list = []
    if node is None: return best_list
    axis = depth % 3
    dist_sq = v_dist_sq(target, node.point)
    inserted = False
    for i, (b_node, b_dist) in enumerate(best_list):
        if dist_sq < b_dist:
            best_list.insert(i, (node, dist_sq))
            inserted = True
            break
    if not inserted and len(best_list) < k:
        best_list.append((node, dist_sq))
    if len(best_list) > k: best_list.pop()
    next_b, oppo_b = (node.left, node.right) if target[axis] < node.point[axis] else (node.right, node.left)
    best_list = kdtree_k_nearest(next_b, target, k, depth + 1, best_list)
    if len(best_list) < k or (target[axis] - node.point[axis])**2 < best_list[-1][1]:
        best_list = kdtree_k_nearest(oppo_b, target, k, depth + 1, best_list)
    return best_list

# ======================================================================
# [ 유틸리티 함수 ]
# ======================================================================
def find_target_ini(folder_path, blend_hash):
    """지정된 폴더 및 하위 폴더에서 해당 얼굴 해시를 포함하는 ini 파일을 찾습니다. (disabled로 시작하면 무시)"""
    for root, dirs, files in os.walk(folder_path):
        # disabled로 시작하는 폴더 무시
        dirs[:] = [d for d in dirs if not d.lower().startswith('disabled')]
        for file in files:
            if file.lower().endswith('.ini') and not file.lower().startswith('disabled'):
                ini_path = os.path.join(root, file)
                try:
                    with open(ini_path, 'r', encoding='utf-8') as f:
                        for line in f:
                            if line.strip().lower() == f"hash = {blend_hash.lower()}":
                                return ini_path
                except:
                    pass
    return None

def resolve_path(input_path, target_type, blend_hash=None):
    """파일 경로 또는 폴더 경로를 받아 적절한 파일 경로로 변환합니다."""
    if not input_path:
        return ""
    if os.path.isfile(input_path) and not os.path.basename(input_path).lower().startswith('disabled'):
        return input_path
    if os.path.isdir(input_path):
        if target_type == 'hash':
            candidate = os.path.join(input_path, "hash.json")
            if os.path.isfile(candidate):
                return candidate
        elif target_type == 'ini' and blend_hash:
            return find_target_ini(input_path, blend_hash) or input_path
    return input_path

def print_progress(current, total, prefix='', length=40):
    """콘솔에 진행률 표시줄을 출력합니다."""
    if total == 0:
        return
    percent = f"{100 * current / total:.1f}"
    filled = int(length * current // total)
    bar = '█' * filled + '-' * (length - filled)
    sys.stdout.write(f'\r{prefix} |{bar}| {percent}% 완료')
    sys.stdout.flush()
    if current == total:
        print()

def prompt(msg):
    """입력 프롬프트: 앞뒤 따옴표와 공백을 제거합니다."""
    return input(msg).strip().strip('"').strip("'")

# ======================================================================
# [ 핵심 로직 함수 ]
# ======================================================================
def find_file_with_hash(folder, hash_val, keyword):
    for f in os.listdir(folder):
        if keyword in f and hash_val in f and f.endswith(".txt"):
            return os.path.join(folder, f)
    return None

def parse_and_get_custom_bufs(ini_path, blend_hash):
    """ini 파일을 파싱하여 여러 프레임의 커스텀 버퍼 파일들을 찾습니다."""
    with open(ini_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    hash_section = None
    in_any_section = None
    
    # 1. 대상 hash가 있는 섹션 이름 찾기
    for line in lines:
        l = line.strip().lower()
        if l.startswith('[') and l.endswith(']'):
            in_any_section = l[1:-1].strip()
        elif l == f"hash = {blend_hash.lower()}":
            hash_section = in_any_section
            
    if not hash_section:
        return [], lines
        
    # 2. CommandList 위임 여부 확인
    target_commands = [hash_section.lower()]
    in_hash_section = False
    for line in lines:
        l = line.strip().lower()
        if l.startswith('[') and l.endswith(']'):
            in_hash_section = (l[1:-1].strip() == hash_section.lower())
        elif in_hash_section and (l.startswith("run ") or l.startswith("run=")):
            run_val = l.split("=", 1)[1].strip()
            if run_val not in target_commands:
                target_commands.append(run_val)
                
    # 3. 리소스 키 수집 (원본 버퍼들)
    resource_keys = [] 
    in_target_cmd = False
    
    for line in lines:
        l = line.strip().lower()
        if l.startswith('[') and l.endswith(']'):
            in_target_cmd = (l[1:-1].strip() in target_commands)
            
        if in_target_cmd:
            if l.startswith("vb0 ") or l.startswith("vb0="):
                res_val = l.split("=", 1)[1].strip()
                if not res_val.startswith("resourcefaceanimated") and res_val not in resource_keys:
                    resource_keys.append(res_val)
            elif l.startswith("cs-u5") and "copy" in l:
                res_val = l.split("copy", 1)[1].strip()
                if res_val != "resourcefaceexpressionbase" and res_val not in resource_keys:
                    resource_keys.append(res_val)
                    
    # 4. 각 리소스 키에 해당하는 filename 찾기
    buffers = [] # (resource_key, filename)
    for res_key in resource_keys:
        in_res = False
        for line in lines:
            l = line.strip().lower()
            if l.startswith('[') and l.endswith(']'):
                in_res = (l[1:-1].strip() == res_key.lower())
            elif in_res and l.startswith("filename"):
                parts = line.split("=", 1)
                if len(parts) == 2:
                    buffers.append((res_key, parts[1].strip()))
                    break
                    
    return buffers, lines

def parse_dump_txt(vb0_path, ib_path, out_buf_path):
    vertices = []
    buf_data = bytearray()
    vertex_count = 0
    current_pos, current_norm, current_tang = [0.0]*3, [0.0]*3, [0.0]*4

    with open(vb0_path, 'r', encoding='utf-8') as f:
        for line in f:
            l = line.strip()
            if l.startswith("vertex count:"):
                vertex_count = int(l.split(":")[1].strip())
            elif "POSITION:" in l:
                current_pos = [float(v.strip()) for v in l.split("POSITION:")[1].strip().split(",")]
                vertices.append(tuple(current_pos))
            elif "NORMAL:" in l:
                current_norm = [float(v.strip()) for v in l.split("NORMAL:")[1].strip().split(",")]
            elif "TANGENT:" in l:
                current_tang = [float(v.strip()) for v in l.split("TANGENT:")[1].strip().split(",")]
                buf_data.extend(struct.pack('<3f', *current_pos))
                buf_data.extend(struct.pack('<3f', *current_norm))
                buf_data.extend(struct.pack('<4f', *current_tang))

    with open(out_buf_path, 'wb') as f:
        f.write(buf_data)

    polygons = []
    skip_prefixes = ("byte", "first", "index", "topology", "format")
    with open(ib_path, 'r', encoding='utf-8') as f:
        for line in f:
            l = line.strip()
            if not l or any(l.startswith(p) for p in skip_prefixes):
                continue
            parts = l.split()
            if len(parts) >= 3:
                polygons.append((int(parts[0]), int(parts[1]), int(parts[2])))

    return vertices, polygons, vertex_count

def build_animation_map(custom_buf_path, orig_vertices, orig_polygons, kdtree, out_map_path, mapping_method, vertex_to_faces=None, progress_prefix='맵핑 진행도: '):
    custom_vertices = []
    with open(custom_buf_path, 'rb') as f:
        while True:
            pos_bytes = f.read(12)
            if len(pos_bytes) < 12:
                break
            f.read(28)
            custom_vertices.append(struct.unpack('<3f', pos_bytes))

    total = len(custom_vertices)
    map_data = bytearray()
    
    for idx, v_pos in enumerate(custom_vertices):
        if idx % 50 == 0 or idx == total - 1:
            print_progress(idx + 1, total, prefix=progress_prefix)

        if mapping_method == 'TOPOLOGY':
            i = min(idx, len(orig_vertices) - 1)
            map_data.extend(struct.pack('<3I 3I 3f 3f', i, 0, 0, 0, 0, 0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0))
            continue

        if mapping_method == 'NEAREST_VERTEX':
            best_list = kdtree_k_nearest(kdtree, v_pos, k=1)
            i = best_list[0][0].index if best_list else 0
            map_data.extend(struct.pack('<3I 3I 3f 3f', i, 0, 0, 0, 0, 0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0))
            continue

        best_list = kdtree_k_nearest(kdtree, v_pos, k=10)
        best_face_idx = -1
        min_face_dist = float('inf')
        
        if vertex_to_faces is None:
            vertex_to_faces = [[] for _ in range(len(orig_vertices))]
            for face_idx, poly in enumerate(orig_polygons):
                for vi in poly:
                    vertex_to_faces[vi].append(face_idx)
        
        for b_node, _ in best_list:
            v_idx = b_node.index
            for face_idx in vertex_to_faces[v_idx]:
                poly = orig_polygons[face_idx]
                p1, p2, p3 = orig_vertices[poly[0]], orig_vertices[poly[1]], orig_vertices[poly[2]]
                dist = point_triangle_distance_sq(v_pos, p1, p2, p3)
                if dist < min_face_dist:
                    min_face_dist = dist
                    best_face_idx = face_idx
                    
        if best_face_idx == -1:
            map_data.extend(struct.pack('<3I 3I 3f 3f', 0, 0, 0, 0, 0, 0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0))
            continue
            
        poly = orig_polygons[best_face_idx]

        if mapping_method == 'NEAREST_FACE_VERTEX':
            dists = [v_dist_sq(v_pos, orig_vertices[i]) for i in poly]
            min_i = poly[dists.index(min(dists))]
            map_data.extend(struct.pack('<3I 3I 3f 3f', min_i, 0, 0, 0, 0, 0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0))
        else:  # NEAREST_FACE_INTERPOLATED
            p1, p2, p3 = orig_vertices[poly[0]], orig_vertices[poly[1]], orig_vertices[poly[2]]
            try:
                w0, w1, w2 = barycentric_weights(v_pos, p1, p2, p3)
            except Exception:
                w0, w1, w2 = 1.0, 0.0, 0.0
            map_data.extend(struct.pack('<3I 3I 3f 3f', poly[0], poly[1], poly[2], 0, 0, 0, w0, w1, w2, 0.0, 0.0, 0.0))

    with open(out_map_path, 'wb') as f:
        f.write(map_data)

    return len(custom_vertices)

def export_hlsl(directory, custom_vtx_count, orig_vtx_count, suffix_idx):
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

float3 residual(uint index) {{
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
            delta += residual(a.first[j]) * a.firstWeights[j];
        if (a.secondWeights[j] != 0)
            delta += residual(a.second[j]) * a.secondWeights[j];
    }}
    Vertex vertex = Output[i];
    vertex.position += delta;
    Output[i] = vertex;
}}
"""
    with open(os.path.join(directory, f"FaceAnimation_{suffix_idx}.hlsl"), 'w', encoding='utf-8') as f:
        f.write(hlsl_code)

def inject_ini(ini_path, lines, custom_buffers, blend_hash):
    hash_section = None
    in_any_section = None
    
    for line in lines:
        l = line.strip().lower()
        if l.startswith('[') and l.endswith(']'):
            in_any_section = l[1:-1].strip()
        elif l == f"hash = {blend_hash.lower()}":
            hash_section = in_any_section
            
    target_commands = [hash_section.lower()] if hash_section else []
    in_hash_section = False
    for line in lines:
        l = line.strip().lower()
        if l.startswith('[') and l.endswith(']'):
            in_hash_section = (l[1:-1].strip() == hash_section.lower()) if hash_section else False
        elif in_hash_section and (l.startswith("run ") or l.startswith("run=")):
            run_val = l.split("=", 1)[1].strip()
            if run_val not in target_commands:
                target_commands.append(run_val)

    out_lines = []
    in_target_cmd = False
    in_draw_type_1 = False

    for line in lines:
        l = line.strip().lower()
        if l.startswith('[') and l.endswith(']'):
            in_target_cmd = (l[1:-1].strip() in target_commands)
            in_draw_type_1 = False

        if in_target_cmd:
            if "if draw_type" in l and "1" in l:
                in_draw_type_1 = True
            elif "endif" in l or "elif" in l:
                in_draw_type_1 = False

            if in_draw_type_1 or not any("if draw_type" in x.lower() for x in lines):
                if (l.startswith("vb0 ") or l.startswith("vb0=")) and "resourcefaceanimated" not in l:
                    res_val = line.split("=", 1)[1].strip()
                    
                    # 현재 vb0가 커스텀 버퍼 목록 중 몇 번째인지 확인
                    idx = -1
                    for j, (rk, _, _) in enumerate(custom_buffers):
                        if rk.lower() == res_val.lower():
                            idx = j
                            break
                            
                    if idx != -1:
                        indent = line[:len(line) - len(line.lstrip())]
                        out_lines.append(f"{indent}run = CustomShaderFaceAnimation_{idx}\n")
                        out_lines.append(f"{indent}vb0 = ResourceFaceAnimated_{idx}\n")
                        continue

        out_lines.append(line)

    appended_ini = "\n; ==========================================================\n; XXMI Face Animation Auto-Injected\n; ==========================================================\n"
    appended_ini += "[ResourceFaceOriginalNeutral]\ntype = StructuredBuffer\nstride = 40\nfilename = FaceOriginalNeutral.buf\n\n"
    appended_ini += "[ResourceFaceLive]\ntype = StructuredBuffer\nstride = 40\n\n"
    
    for idx, (res_key, buf_filename, v_count) in enumerate(custom_buffers):
        dispatch_groups = math.ceil(v_count / 64.0)
        block = f"""[CustomShaderFaceAnimation_{idx}]
cs = FaceAnimation_{idx}.hlsl
ResourceFaceLive = copy vb0
cs-t50 = ref ResourceFaceLive
cs-t51 = ref ResourceFaceOriginalNeutral
cs-t52 = ref ResourceFaceAnimationMap_{idx}
cs-u5 = copy ResourceCustomFaceExtracted_{idx}
ResourceFaceAnimated_{idx} = ref cs-u5
Dispatch = {dispatch_groups}, 1, 1
cs-u5 = null
cs-t50 = null
cs-t51 = null
cs-t52 = null

[ResourceFaceAnimated_{idx}]

[ResourceFaceAnimationMap_{idx}]
type = StructuredBuffer
stride = 48
filename = FaceAnimationMap_{idx}.buf

[ResourceCustomFaceExtracted_{idx}]
type = StructuredBuffer
stride = 40
filename = {buf_filename}

"""
        appended_ini += block
    appended_ini += "; ==========================================================\n"
    out_lines.append(appended_ini)

    with open(ini_path, 'w', encoding='utf-8') as f:
        f.writelines(out_lines)

def do_rollback(ini_path, silent=False):
    if not os.path.isfile(ini_path):
        if not silent: print("[ERROR] 올바른 mod.ini 경로가 아닙니다.")
        return

    mod_folder = os.path.dirname(ini_path)

    map_pattern = re.compile(r"^FaceAnimationMap_\d+\.buf$")
    hlsl_pattern = re.compile(r"^FaceAnimation_\d+\.hlsl$")
    
    try:
        for fname in os.listdir(mod_folder):
            if fname in ("FaceOriginalNeutral.buf", "FaceAnimationMap.buf", "FaceAnimation.hlsl") or map_pattern.match(fname) or hlsl_pattern.match(fname):
                fpath = os.path.join(mod_folder, fname)
                os.remove(fpath)
                if not silent: print(f"[삭제됨] {fname}")
    except Exception as e:
        if not silent: print(f"[삭제 실패]: {e}")

    with open(ini_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    extracted_files = {}
    current_idx = None
    for line in lines:
        l = line.strip().lower()
        if l.startswith('[') and l.endswith(']'):
            sec = l[1:-1].strip()
            if sec.startswith("resourcecustomfaceextracted"):
                parts = sec.split("_")
                current_idx = parts[-1] if len(parts) > 1 and parts[-1].isdigit() else ""
            else:
                current_idx = None
        elif current_idx is not None and l.startswith("filename"):
            parts = line.split('=', 1)
            if len(parts) == 2:
                extracted_files[current_idx] = parts[1].strip().lower().replace('\\', '/')

    orig_resources = {}
    current_res = None
    for line in lines:
        l = line.strip()
        if l.startswith('[') and l.endswith(']'):
            current_res = l[1:-1].strip()
        elif current_res and not current_res.lower().startswith('resourcecustomfaceextracted') and l.lower().startswith('filename'):
            parts = line.split('=', 1)
            if len(parts) == 2:
                fname = parts[1].strip().lower().replace('\\', '/')
                for idx, ex_fname in extracted_files.items():
                    if fname == ex_fname:
                        orig_resources[idx] = current_res

    out_lines = []
    for line in lines:
        l = line.strip().lower()
        if l == "; xxmi face animation auto-injected":
            while out_lines and out_lines[-1].strip() in ("", "; =========================================================="):
                out_lines.pop()
            break  
            
        if l.startswith("run ") and "customshaderfaceanimation" in l:
            continue
            
        if l.startswith("vb0 ") or l.startswith("vb0="):
            if "resourcefaceanimated" in l:
                res_val = line.split("=", 1)[1].strip()
                parts = res_val.split("_")
                idx = parts[-1] if len(parts) > 1 and parts[-1].isdigit() else ""
                
                orig_res = orig_resources.get(idx)
                if orig_res:
                    indent = line[:len(line) - len(line.lstrip())]
                    out_lines.append(f"{indent}vb0 = {orig_res}\n")
                continue
                
        out_lines.append(line)

    with open(ini_path, 'w', encoding='utf-8') as f:
        f.writelines(out_lines)

    if not silent: print("[완료] 롤백이 완료되었습니다.")

def run_apply(hash_path, ini_input_path, component, method):
    """표정 연동 적용 핵심 로직"""
    dump_folder = os.path.dirname(hash_path)

    with open(hash_path, 'r', encoding='utf-8') as f:
        hash_data = json.load(f)

    comp_data = next((c for c in hash_data if c.get("component_name") == component), None)
    if not comp_data:
        print(f"[ERROR] hash.json에서 '{component}' 컴포넌트를 찾을 수 없습니다.")
        return

    pos_vb_hash  = comp_data.get("position_vb")
    ib_hash      = comp_data.get("ib")
    blend_vb_hash = comp_data.get("blend_vb")

    if not pos_vb_hash or not ib_hash:
        print("[ERROR] 컴포넌트에 필요한 해시(position_vb, ib)가 부족합니다.")
        return
        
    ini_path = resolve_path(ini_input_path, 'ini', blend_vb_hash)
    if not os.path.isfile(ini_path):
        print(f"[ERROR] {ini_input_path} 경로에서 얼굴 컴포넌트(hash={blend_vb_hash})가 있는 유효한 ini 파일을 찾을 수 없습니다.")
        return
        
    mod_folder  = os.path.dirname(ini_path)
    
    # 혹시 이전에 작업된 흔적이 있다면 초기화부터 한다
    do_rollback(ini_path, silent=True)

    vb0_txt = find_file_with_hash(dump_folder, pos_vb_hash, "-vb0=")
    ib_txt  = find_file_with_hash(dump_folder, ib_hash, "-ib=")
    if not vb0_txt or not ib_txt:
        print(f"[ERROR] 에셋 폴더에서 '{component}'의 -vb0 또는 -ib 텍스트 파일을 찾을 수 없습니다.")
        return

    buffers_list, ini_lines = parse_and_get_custom_bufs(ini_path, blend_vb_hash)
    if not buffers_list:
        print("[ERROR] ini 파일에서 커스텀 얼굴 버퍼를 추적할 수 없습니다.")
        return

    orig_vertices, orig_polygons, orig_vertex_count = parse_dump_txt(
        vb0_txt, ib_txt, os.path.join(mod_folder, "FaceOriginalNeutral.buf")
    )
    print(f"원본 메쉬 분석 완료: {orig_vertex_count} 버텍스")

    print("KD-Tree 생성 중...")
    kdtree = build_kdtree([(v, i) for i, v in enumerate(orig_vertices)])
    
    vertex_to_faces = None
    if method != 'NEAREST_VERTEX':
        vertex_to_faces = [[] for _ in range(len(orig_vertices))]
        for face_idx, poly in enumerate(orig_polygons):
            for v_idx in poly:
                vertex_to_faces[v_idx].append(face_idx)

    print(f"총 {len(buffers_list)}개의 얼굴 버퍼(프레임)가 감지되었습니다.")
    
    custom_buffers_info = [] # (resource_key, buf_filename, custom_vtx_count)
    
    for idx, (res_key, buf_filename) in enumerate(buffers_list):
        custom_buf_path = os.path.join(mod_folder, buf_filename)
        if not os.path.isfile(custom_buf_path):
            print(f"[ERROR] 커스텀 버퍼 파일이 존재하지 않습니다: {buf_filename}")
            return
            
        print(f"\n[{idx+1}/{len(buffers_list)}] '{buf_filename}' 처리 중...")
        custom_vertex_count = build_animation_map(
            custom_buf_path, orig_vertices, orig_polygons, kdtree,
            os.path.join(mod_folder, f"FaceAnimationMap_{idx}.buf"), method, progress_prefix=f'[{idx+1}/{len(buffers_list)}] 맵핑:'
        )
        export_hlsl(mod_folder, custom_vertex_count, orig_vertex_count, idx)
        
        custom_buffers_info.append((res_key, buf_filename, custom_vertex_count))
        
    inject_ini(ini_path, ini_lines, custom_buffers_info, blend_vb_hash)

    print("\n[완료] 모드 폴더에 버퍼와 쉐이더가 성공적으로 생성 및 적용되었습니다.")

# ======================================================================
# [ 메인 로직 ]
# ======================================================================
METHODS = {
    "1": "TOPOLOGY",
    "2": "NEAREST_VERTEX",
    "3": "NEAREST_FACE_VERTEX",
    "4": "NEAREST_FACE_INTERPOLATED",
}
METHOD_HELP = (
    "맵핑 방식을 선택합니다. 사용 가능한 값:\n"
    "  TOPOLOGY                  - 동일한 버텍스 인덱스를 1:1 매칭\n"
    "  NEAREST_VERTEX            - 가장 가까운 버텍스 1개에 100%% 매핑\n"
    "  NEAREST_FACE_VERTEX       - 가장 가까운 면의 꼭짓점 중 하나에 매핑\n"
    "  NEAREST_FACE_INTERPOLATED - (기본/추천) 가장 가까운 면의 3개 꼭짓점에\n"
    "                              무게중심 가중치로 분배"
)

def interactive_apply():
    """인자 없이 실행 시 단계별 안내와 함께 표정 연동을 진행합니다."""
    print("\n[ 표정 연동 적용 ]")
    print("-" * 40)

    hash_path = resolve_path(prompt("[1/4] dump 폴더(또는 hash.json) 경로: "), 'hash')
    if not os.path.isfile(hash_path):
        print("[ERROR] hash.json 파일을 찾을 수 없습니다."); return

    # hash.json을 미리 읽어서 컴포넌트 목록 표시
    try:
        with open(hash_path, 'r', encoding='utf-8') as f:
            hash_data = json.load(f)
        component_names = [c.get("component_name", f"(이름 없음 #{i})") for i, c in enumerate(hash_data)]
    except Exception as e:
        print(f"[ERROR] hash.json을 읽을 수 없습니다: {e}"); return

    print("[2/4] 컴포넌트를 선택하세요:")
    for i, name in enumerate(component_names, 1):
        marker = " ← (기본)" if name == "Face" else ""
        print(f"  {i}. {name}{marker}")
    comp_input = prompt("번호 또는 이름을 입력하세요 (비워두면 'Face' 사용): ")

    if not comp_input:
        component = "Face"
    elif comp_input.isdigit():
        idx = int(comp_input) - 1
        if 0 <= idx < len(component_names):
            component = component_names[idx]
        else:
            print("[ERROR] 유효하지 않은 번호입니다."); return
    else:
        component = comp_input
    print(f"     → '{component}' 선택됨\n")
    
    # 3단계: 모드 폴더를 선택하면, 내부에서 블렌드 해시를 기반으로 적절한 ini 파일을 자동 탐색
    ini_input_path = prompt("[3/4] 타겟 모드 폴더(또는 mod.ini) 경로: ")

    print("[4/4] 맵핑 방식을 선택하세요:")
    print("  1. TOPOLOGY                  - 동일한 버텍스 인덱스를 1:1로 직접 매칭합니다.")
    print("                                 원본과 커스텀 메쉬의 버텍스 순서가 동일할 때만 정확합니다.")
    print("  2. NEAREST_VERTEX            - 가장 가까운 버텍스 1개에 100%% 매핑합니다.")
    print("                                 빠르지만 표현이 부드럽지 않을 수 있습니다.")
    print("  3. NEAREST_FACE_VERTEX       - 가장 가까운 면의 꼭짓점 중 하나에 매핑합니다.")
    print("                                 NEAREST_VERTEX보다 면 정보를 활용해 조금 더 정확합니다.")
    print("  4. NEAREST_FACE_INTERPOLATED - (기본/추천) 가장 가까운 면의 꼭짓점 3개에")
    print("                                 무게중심 가중치로 분배합니다. 가장 부드럽고 자연스럽습니다.")
    method_choice = prompt("번호 입력 (비워두면 4번 선택): ") or "4"
    method = METHODS.get(method_choice, "NEAREST_FACE_INTERPOLATED")
    print(f"     → {method} 선택됨\n")

    try:
        run_apply(hash_path, ini_input_path, component, method)
    except Exception as e:
        traceback.print_exc()
        print(f"[ERROR] {e}")

def interactive_rollback():
    """인자 없이 실행 시 대화형 롤백을 진행합니다."""
    print("\n[ 롤백 ]")
    print("-" * 40)
    # 롤백 시에는 그냥 무조건 첫번째로 찾아지는 ini 혹은 입력한 ini를 사용
    # 여기서는 해시를 모르므로 하위 폴더의 모든 ini에 대해 롤백 시도
    ini_input = prompt("[1/1] 모드 폴더(또는 mod.ini) 경로: ")
    if os.path.isfile(ini_input):
        do_rollback(ini_input)
    elif os.path.isdir(ini_input):
        found = False
        for root, dirs, files in os.walk(ini_input):
            dirs[:] = [d for d in dirs if not d.lower().startswith('disabled')]
            for file in files:
                if file.lower().endswith('.ini') and not file.lower().startswith('disabled'):
                    do_rollback(os.path.join(root, file))
                    found = True
        if not found:
            print("[ERROR] 롤백할 .ini 파일을 찾을 수 없습니다.")
    else:
        print("[ERROR] 유효하지 않은 경로입니다.")

def main():
    parser = argparse.ArgumentParser(
        description="XXMI Face Animation Standalone (Pure Python)",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--hash",      help="dump 폴더 또는 hash.json 경로", default=None)
    parser.add_argument("--ini",       help="모드 폴더 또는 mod.ini 경로",   default=None)
    parser.add_argument("--component", help="컴포넌트 이름 (기본: Face)",    default="Face", metavar='NAME')
    parser.add_argument("--method",    help=METHOD_HELP,                      default="NEAREST_FACE_INTERPOLATED")
    parser.add_argument("--rollback",  help="적용했던 파일과 ini 수정을 원상 복구합니다.", action="store_true")
    args, _ = parser.parse_known_args()

    # 인자로 직접 실행하는 경우 (비대화형)
    if args.rollback and args.ini:
        if os.path.isfile(args.ini):
            do_rollback(args.ini)
        elif os.path.isdir(args.ini):
            for root, dirs, files in os.walk(args.ini):
                dirs[:] = [d for d in dirs if not d.lower().startswith('disabled')]
                for file in files:
                    if file.lower().endswith('.ini') and not file.lower().startswith('disabled'):
                        do_rollback(os.path.join(root, file))
        return

    if args.hash and args.ini:
        hash_path = resolve_path(args.hash, 'hash')
        if not os.path.isfile(hash_path):
            print("[ERROR] hash.json 파일을 찾을 수 없습니다."); return
        try:
            run_apply(hash_path, args.ini, args.component, args.method)
        except Exception as e:
            traceback.print_exc()
            print(f"[ERROR] {e}")
        return

    # 인자가 없으면 대화형 메뉴
    print("=" * 40)
    print("  XXMI Face Animation 매핑 툴")
    print("=" * 40)
    print("  1. 표정 연동 적용")
    print("  2. 롤백 (적용 내용 되돌리기)")
    print("=" * 40)
    choice = prompt("원하는 작업 번호를 입력하세요: ")

    if choice == "1":
        interactive_apply()
    elif choice == "2":
        interactive_rollback()
    else:
        print("[ERROR] 1 또는 2를 입력하세요.")

if __name__ == "__main__":
    main()
    input("\n종료하려면 엔터 키를 누르세요...")
