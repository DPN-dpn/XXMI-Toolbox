import sys
import struct
import os
import json
import math
import traceback
import argparse

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
def v_dist_sq(a, b): return (a[0]-b[0])**2 + (a[1]-b[1])**2 + (a[2]-b[2])**2

def barycentric_weights(p, a, b, c):
    v0, v1, v2 = v_sub(b, a), v_sub(c, a), v_sub(p, a)
    d00, d01, d11 = v_dot(v0, v0), v_dot(v0, v1), v_dot(v1, v1)
    d20, d21 = v_dot(v2, v0), v_dot(v2, v1)
    denom = d00 * d11 - d01 * d01
    if denom == 0:
        return 1.0, 0.0, 0.0
    v = (d11 * d20 - d01 * d21) / denom
    w = (d00 * d21 - d01 * d20) / denom
    return 1.0 - v - w, v, w

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

def kdtree_nearest(node, target, depth=0, best=None):
    if node is None:
        return best
    axis = depth % 3
    dist_sq = v_dist_sq(target, node.point)
    if best is None or dist_sq < best[1]:
        best = (node, dist_sq)
    next_b, oppo_b = (node.left, node.right) if target[axis] < node.point[axis] else (node.right, node.left)
    best = kdtree_nearest(next_b, target, depth + 1, best)
    if (target[axis] - node.point[axis])**2 < best[1]:
        best = kdtree_nearest(oppo_b, target, depth + 1, best)
    return best

# ======================================================================
# [ 유틸리티 함수 ]
# ======================================================================
def resolve_path(input_path, target_type):
    """파일 경로 또는 폴더 경로를 받아 적절한 파일 경로로 변환합니다."""
    if not input_path:
        return ""
    if os.path.isfile(input_path):
        return input_path
    if os.path.isdir(input_path):
        if target_type == 'hash':
            candidate = os.path.join(input_path, "hash.json")
            if os.path.isfile(candidate):
                return candidate
        elif target_type == 'ini':
            # mod.ini 우선, 없으면 임의의 .ini 파일 탐색
            candidate = os.path.join(input_path, "mod.ini")
            if os.path.isfile(candidate):
                return candidate
            for f in os.listdir(input_path):
                if f.lower().endswith(".ini"):
                    return os.path.join(input_path, f)
    return input_path

def print_progress(current, total, prefix='', length=40):
    """콘솔에 진행률 표시줄을 출력합니다."""
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

def parse_and_get_custom_buf(ini_path, blend_hash):
    with open(ini_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    in_target_section = False
    resource_key = None

    for line in lines:
        l = line.strip().lower()
        if l.startswith('[') and l.endswith(']'):
            in_target_section = False
        if l == f"hash = {blend_hash.lower()}":
            in_target_section = True
        if not in_target_section:
            continue

        if (l.startswith("vb0 ") or l.startswith("vb0=")) and not resource_key:
            res_val = l.split("=", 1)[1].strip()
            if res_val != "resourcefaceanimated":
                resource_key = res_val
        elif l.startswith("cs-u5") and "copy" in l and not resource_key:
            resource_key = l.split("copy", 1)[1].strip()

    if not resource_key:
        return None, lines

    in_res_section = False
    for line in lines:
        l = line.strip()
        if l.startswith('[') and l.endswith(']'):
            in_res_section = (l[1:-1].strip().lower() == resource_key.lower())
        if in_res_section and l.lower().startswith("filename"):
            custom_buf_name = l.split("=", 1)[1].strip()
            return custom_buf_name, lines

    return None, lines

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

def build_animation_map(custom_buf_path, orig_vertices, orig_polygons, out_map_path, mapping_method):
    print("KD-Tree 생성 중...")

    if mapping_method == 'NEAREST_VERTEX':
        kdtree = build_kdtree([(v, i) for i, v in enumerate(orig_vertices)])
    else:
        # 면 기준 매핑: 각 삼각형의 무게중심을 트리에 등록
        centroids = [
            (((orig_vertices[p[0]][0]+orig_vertices[p[1]][0]+orig_vertices[p[2]][0])/3,
              (orig_vertices[p[0]][1]+orig_vertices[p[1]][1]+orig_vertices[p[2]][1])/3,
              (orig_vertices[p[0]][2]+orig_vertices[p[1]][2]+orig_vertices[p[2]][2])/3), i)
            for i, p in enumerate(orig_polygons)
        ]
        kdtree = build_kdtree(centroids)

    # 커스텀 버퍼의 버텍스 위치 로드 (stride=40: pos(12)+norm(12)+rest(16))
    custom_vertices = []
    with open(custom_buf_path, 'rb') as f:
        while True:
            pos_bytes = f.read(12)
            if len(pos_bytes) < 12:
                break
            f.read(28)
            custom_vertices.append(struct.unpack('<3f', pos_bytes))

    total = len(custom_vertices)
    print(f"커스텀 버텍스 맵핑 시작 (총 {total}개)...")

    map_data = bytearray()
    for idx, v_pos in enumerate(custom_vertices):
        if idx % 100 == 0 or idx == total - 1:
            print_progress(idx + 1, total, prefix='맵핑 진행률:')

        if mapping_method == 'TOPOLOGY':
            i = min(idx, len(orig_vertices) - 1)
            map_data.extend(struct.pack('<3I 3I 3f 3f', i, 0, 0, 0, 0, 0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0))
            continue

        nearest_node, _ = kdtree_nearest(kdtree, v_pos)

        if mapping_method == 'NEAREST_VERTEX':
            i = nearest_node.index
            map_data.extend(struct.pack('<3I 3I 3f 3f', i, 0, 0, 0, 0, 0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0))
            continue

        poly = orig_polygons[nearest_node.index]

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

def export_hlsl(directory, custom_vtx_count, orig_vtx_count):
    dispatch_groups = math.ceil(custom_vtx_count / 64.0)
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
    with open(os.path.join(directory, "FaceAnimation.hlsl"), 'w', encoding='utf-8') as f:
        f.write(hlsl_code)

def inject_ini(ini_path, lines, custom_buf_name, blend_hash):
    # 이미 적용되어 있으면 vb0/run 수정만 한다
    has_custom_shader = any("[CustomShaderFaceAnimation]" in l for l in lines)

    out_lines = []
    in_target_section = False
    in_draw_type_1 = False

    for line in lines:
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
                in_draw_type_1 = False

            if in_draw_type_1:
                if (l.startswith("vb0 ") or l.startswith("vb0=")) and "resourcefaceanimated" not in l:
                    indent = line[:len(line) - len(line.lstrip())]
                    out_lines.append(f"{indent}run = CustomShaderFaceAnimation\n")
                    out_lines.append(f"{indent}vb0 = ResourceFaceAnimated\n")
                    continue
                if l.startswith("run ") and "customshaderfaceanimation" in l:
                    continue

        out_lines.append(line)

    if not has_custom_shader:
        custom_size = os.path.getsize(os.path.join(os.path.dirname(ini_path), custom_buf_name))
        dispatch_groups = math.ceil((custom_size // 40) / 64.0)
        out_lines.append(f"""
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
""")

    with open(ini_path, 'w', encoding='utf-8') as f:
        f.writelines(out_lines)

def do_rollback(ini_path):
    if not os.path.isfile(ini_path):
        print("[ERROR] 올바른 mod.ini 경로가 아닙니다.")
        return

    mod_folder = os.path.dirname(ini_path)

    for fname in ["FaceOriginalNeutral.buf", "FaceAnimationMap.buf", "FaceAnimation.hlsl"]:
        fpath = os.path.join(mod_folder, fname)
        if os.path.exists(fpath):
            try:
                os.remove(fpath)
                print(f"[삭제됨] {fname}")
            except Exception as e:
                print(f"[삭제 실패] {fname}: {e}")

    with open(ini_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    out_lines = []
    for line in lines:
        l = line.strip().lower()
        if l in ("run = customshaderfaceanimation", "vb0 = resourcefaceanimated"):
            continue
        if l == "; xxmi face animation auto-injected":
            # 이전에 추가한 구분선과 빈 줄 제거
            while out_lines and out_lines[-1].strip() in ("", "; =========================================================="):
                out_lines.pop()
            break  # 이 줄부터 아래는 스크립트가 추가한 블록이므로 전부 무시
        out_lines.append(line)

    with open(ini_path, 'w', encoding='utf-8') as f:
        f.writelines(out_lines)

    print("[완료] 롤백이 완료되었습니다.")

def run_apply(hash_path, ini_path, component, method):
    """표정 연동 적용 핵심 로직"""
    dump_folder = os.path.dirname(hash_path)
    mod_folder  = os.path.dirname(ini_path)

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

    vb0_txt = find_file_with_hash(dump_folder, pos_vb_hash, "-vb0=")
    ib_txt  = find_file_with_hash(dump_folder, ib_hash, "-ib=")
    if not vb0_txt or not ib_txt:
        print(f"[ERROR] 에셋 폴더에서 '{component}'의 -vb0 또는 -ib 텍스트 파일을 찾을 수 없습니다.")
        return

    custom_buf_name, ini_lines = parse_and_get_custom_buf(ini_path, blend_vb_hash)
    if not custom_buf_name:
        print("[ERROR] ini 파일에서 커스텀 얼굴 버퍼를 추적할 수 없습니다.")
        return

    custom_buf_path = os.path.join(mod_folder, custom_buf_name)
    if not os.path.isfile(custom_buf_path):
        print(f"[ERROR] 커스텀 버퍼 파일이 존재하지 않습니다: {custom_buf_name}")
        return

    orig_vertices, orig_polygons, orig_vertex_count = parse_dump_txt(
        vb0_txt, ib_txt, os.path.join(mod_folder, "FaceOriginalNeutral.buf")
    )
    print(f"원본 메쉬 분석 완료: {orig_vertex_count} 버텍스")

    custom_vertex_count = build_animation_map(
        custom_buf_path, orig_vertices, orig_polygons,
        os.path.join(mod_folder, "FaceAnimationMap.buf"), method
    )
    export_hlsl(mod_folder, custom_vertex_count, orig_vertex_count)
    inject_ini(ini_path, ini_lines, custom_buf_name, blend_vb_hash)

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

    hash_path = resolve_path(prompt("[1/4] 에셋 폴더(또는 hash.json) 경로: "), 'hash')
    if not os.path.isfile(hash_path):
        print("[ERROR] hash.json 파일을 찾을 수 없습니다."); return

    ini_path = resolve_path(prompt("[2/4] 모드 폴더(또는 mod.ini) 경로: "), 'ini')
    if not os.path.isfile(ini_path):
        print("[ERROR] ini 파일을 찾을 수 없습니다."); return

    # hash.json을 미리 읽어서 컴포넌트 목록 표시
    try:
        with open(hash_path, 'r', encoding='utf-8') as f:
            hash_data = json.load(f)
        component_names = [c.get("component_name", f"(이름 없음 #{i})") for i, c in enumerate(hash_data)]
    except Exception as e:
        print(f"[ERROR] hash.json을 읽을 수 없습니다: {e}"); return

    print("[3/4] 컴포넌트를 선택하세요:")
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
        component = comp_input  # 직접 이름 입력도 허용
    print(f"     → '{component}' 선택됨\n")

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
        run_apply(hash_path, ini_path, component, method)
    except Exception as e:
        traceback.print_exc()
        print(f"[ERROR] {e}")

def interactive_rollback():
    """인자 없이 실행 시 대화형 롤백을 진행합니다."""
    print("\n[ 롤백 ]")
    print("-" * 40)
    ini_path = resolve_path(prompt("[1/1] 모드 폴더(또는 mod.ini) 경로: "), 'ini')
    try:
        do_rollback(ini_path)
    except Exception as e:
        traceback.print_exc()
        print(f"[ERROR] {e}")

def main():
    parser = argparse.ArgumentParser(
        description="XXMI Face Animation Standalone (Pure Python)",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--hash",      help="에셋 폴더 또는 hash.json 경로", default=None)
    parser.add_argument("--ini",       help="모드 폴더 또는 mod.ini 경로",   default=None)
    parser.add_argument("--component", help="컴포넌트 이름 (기본: Face)",    default="Face", metavar='NAME')
    parser.add_argument("--method",    help=METHOD_HELP,                      default="NEAREST_FACE_INTERPOLATED")
    parser.add_argument("--rollback",  help="적용했던 파일과 ini 수정을 원상 복구합니다.", action="store_true")
    args, _ = parser.parse_known_args()

    # 인자로 직접 실행하는 경우 (비대화형)
    if args.rollback and args.ini:
        ini_path = resolve_path(args.ini, 'ini')
        try:
            do_rollback(ini_path)
        except Exception as e:
            traceback.print_exc()
            print(f"[ERROR] {e}")
        return

    if args.hash and args.ini:
        hash_path = resolve_path(args.hash, 'hash')
        ini_path  = resolve_path(args.ini, 'ini')
        if not os.path.isfile(hash_path):
            print("[ERROR] hash.json 파일을 찾을 수 없습니다."); return
        if not os.path.isfile(ini_path):
            print("[ERROR] mod.ini 파일을 찾을 수 없습니다."); return
        try:
            run_apply(hash_path, ini_path, args.component, args.method)
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
