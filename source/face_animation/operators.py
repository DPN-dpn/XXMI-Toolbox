import bpy
import struct
import os
import re
import json
import math
from mathutils import Vector
from mathutils.bvhtree import BVHTree

class XXMI_OT_export_face_animation(bpy.types.Operator):
    bl_idname = "object.xxmi_export_face_animation"
    bl_label = "표정 연동 실행"
    bl_description = "선택된 파일들을 분석하여 표정 연동 데이터를 생성하고 ini 파일을 수정합니다"
    
    def execute(self, context):
        props = context.scene.xxmi_face_anim_props
        
        dump_hash_json = props.dump_hash_json
        selected_comp = props.selected_component
        target_ini = props.target_ini
        
        if not os.path.isfile(dump_hash_json):
            self.report({'ERROR'}, "에셋 hash.json 파일을 올바르게 지정해주세요.")
            return {'CANCELLED'}
            
        dump_folder = os.path.dirname(dump_hash_json)
        
        if selected_comp == "NONE":
            self.report({'ERROR'}, "얼굴 컴포넌트를 선택해주세요.")
            return {'CANCELLED'}
            
        if not os.path.isfile(target_ini):
            self.report({'ERROR'}, "타겟 모드 ini 파일을 올바르게 지정해주세요.")
            return {'CANCELLED'}
            
        try:
            # 1. hash.json 파싱
            hash_path = os.path.join(dump_folder, "hash.json")
            with open(hash_path, 'r', encoding='utf-8') as f:
                hash_data = json.load(f)
                
            comp_data = next((c for c in hash_data if c.get("component_name") == selected_comp), None)
            if not comp_data:
                self.report({'ERROR'}, f"hash.json에서 {selected_comp} 컴포넌트를 찾을 수 없습니다.")
                return {'CANCELLED'}
                
            pos_vb_hash = comp_data.get("position_vb")
            ib_hash = comp_data.get("ib")
            blend_vb_hash = comp_data.get("blend_vb")
            
            if not pos_vb_hash or not ib_hash:
                self.report({'ERROR'}, "컴포넌트에 필요한 해시(position_vb, ib)가 부족합니다.")
                return {'CANCELLED'}
                
            # 2. 덤프 텍스트 파일 찾기
            vb0_txt = self.find_file_with_hash(dump_folder, pos_vb_hash, "-vb0=")
            ib_txt = self.find_file_with_hash(dump_folder, ib_hash, "-ib=")
            
            if not vb0_txt or not ib_txt:
                self.report({'ERROR'}, f"에셋 폴더에서 {selected_comp}의 -vb0 또는 -ib 텍스트 파일을 찾을 수 없습니다.")
                return {'CANCELLED'}
                
            # 3. .ini 파싱 및 커스텀 buf 경로 추적
            custom_buf_name, ini_lines = self.parse_and_get_custom_buf(target_ini, blend_vb_hash)
            if not custom_buf_name:
                self.report({'ERROR'}, "ini 파일에서 커스텀 얼굴 버퍼를 추적할 수 없습니다.")
                return {'CANCELLED'}
                
            mod_folder = os.path.dirname(target_ini)
            custom_buf_path = os.path.join(mod_folder, custom_buf_name)
            if not os.path.isfile(custom_buf_path):
                self.report({'ERROR'}, f"커스텀 버퍼 파일이 존재하지 않습니다: {custom_buf_name}")
                return {'CANCELLED'}
                
            # 4. txt 파싱 및 BVHTree 생성, FaceOriginalNeutral.buf 굽기
            orig_vertices, orig_polygons, orig_vertex_count = self.parse_dump_txt(vb0_txt, ib_txt, os.path.join(mod_folder, "FaceOriginalNeutral.buf"))
            
            bvh_vertices = orig_vertices
            if props.aligned_orig_base:
                mesh = props.aligned_orig_base.data
                if len(mesh.vertices) == orig_vertex_count:
                    # 유저가 눈코입을 맞춰둔 오브젝트의 좌표를 사용하여 BVHTree 생성!
                    bvh_vertices = [v.co for v in mesh.vertices]
                else:
                    self.report({'WARNING'}, f"형태 맞춤 오브젝트의 버텍스 개수({len(mesh.vertices)})가 덤프({orig_vertex_count})와 다릅니다. 원본 좌표를 사용합니다.")
                    
            bvh = BVHTree.FromPolygons(bvh_vertices, orig_polygons)
            
            # 5. FaceAnimationMap.buf 굽기
            custom_vertex_count = self.build_animation_map(custom_buf_path, bvh, bvh_vertices, orig_polygons, os.path.join(mod_folder, "FaceAnimationMap.buf"), props.mapping_method)
            
            # 6. HLSL 생성
            self.export_hlsl(mod_folder, props.use_custom_blink, custom_vertex_count, orig_vertex_count)
            
            # 7. INI 주입 (Inject)
            self.inject_ini(target_ini, ini_lines, custom_buf_name, blend_vb_hash, props.use_custom_blink)
            
            # 완료 알림
            def draw_popup(self, context):
                self.layout.label(text="[표정 연동 완료]", icon='INFO')
                self.layout.label(text="모드 폴더에 버퍼와 쉐이더가 성공적으로 생성되었습니다.")
                self.layout.label(text="모드 ini 파일에 쉐이더 구문이 적용되었습니다.")

            context.window_manager.popup_menu(draw_popup, title="연동 완료", icon='INFO')
            self.report({'INFO'}, "표정 연동이 완료되었습니다.")
            return {'FINISHED'}
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.report({'ERROR'}, f"에러 발생: {str(e)}")
            return {'CANCELLED'}
            
    def find_file_with_hash(self, folder, hash_val, keyword):
        for f in os.listdir(folder):
            if keyword in f and hash_val in f and f.endswith(".txt"):
                return os.path.join(folder, f)
        return None
        
    def parse_and_get_custom_buf(self, ini_path, blend_hash):
        with open(ini_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
        in_target_section = False
        resource_key = None
        custom_buf_name = None
        
        # 1차 패스: TextureOverride에서 vb0 리소스 이름 찾기
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
                        # 사용자가 수정한 파일이 아닌 순정 상태라면 원래 리소스를 저장
                        if res_val.lower() != "resourcefaceanimated":
                            resource_key = res_val
                            
            # 만약 이미 주입된 파일이라면 [CustomShaderFaceAnimation] 섹션 근처에 cs-u5 가 있음
            # 이건 섹션 상관없이 전역으로 찾아도 무방함
            if l.startswith("cs-u5") and "copy" in l:
                parts = l.split("copy", 1)
                if len(parts) == 2:
                    potential_key = parts[1].strip()
                    if potential_key.lower() != "resourcefaceexpressionbase": 
                        # 만약 템플릿의 기본값이 아니라면 이걸 사용 (주입된 상태)
                        # 단, 리소스 키가 없을 때만 덮어씀
                        if not resource_key:
                            resource_key = potential_key
                    else:
                        # 템플릿 기본값이어도 resource_key가 없으면 쓴다.
                        if not resource_key:
                            resource_key = potential_key
                            
        if not resource_key:
            return None, lines
            
        # 2차 패스: Resource 섹션에서 filename 찾기
        in_res_section = False
        for line in lines:
            l = line.strip()
            if l.startswith('[') and l.endswith(']'):
                # 대소문자 구분 없이 비교
                in_res_section = (l[1:-1].strip().lower() == resource_key.lower())
                
            if in_res_section and l.lower().startswith("filename"):
                parts = l.split("=", 1)
                if len(parts) == 2:
                    custom_buf_name = parts[1].strip()
                    break
                    
        return custom_buf_name, lines
        
    def parse_dump_txt(self, vb0_path, ib_path, out_buf_path):
        vertices = []
        buf_data = bytearray()
        vertex_count = 0
        
        # vb0.txt 파싱 및 buf 생성
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
                    
                    # TANGENT까지 읽었으면 버퍼에 쓴다 (순서: POS, NORM, TANG)
                    buf_data.extend(struct.pack('<3f', *current_pos))
                    buf_data.extend(struct.pack('<3f', *current_norm))
                    buf_data.extend(struct.pack('<4f', *current_tang))
                    
        with open(out_buf_path, 'wb') as f:
            f.write(buf_data)
            
        # ib.txt 파싱
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
        
    def build_animation_map(self, custom_buf_path, bvh, orig_vertices, orig_polygons, out_map_path, mapping_method):
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

    def export_hlsl(self, directory, use_custom_blink, custom_vtx_count, orig_vtx_count):
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
"""

        hlsl_code += """
float blinkAmount(uint probe) {
    return 0.0;
}

float3 residual(uint index, float2 blink) {
    return Live[index].position - Neutral[index].position;
}
"""

        hlsl_code += f"""
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
            
    def inject_ini(self, ini_path, lines, custom_buf_name, blend_hash, use_custom_blink):
        # 1. 파일 상단에 [CustomShaderFaceAnimation] 및 Resource 자동 추가
        # 이미 있는지 확인
        has_custom_shader = False
        for l in lines:
            if "[CustomShaderFaceAnimation]" in l:
                has_custom_shader = True
                break
                
        # 2. [TextureOverride] 섹션 내 수정
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
                        
                # 덮어쓰기 로직
                if in_draw_type_1:
                    # vb0 수정
                    if l.startswith("vb0 ") or l.startswith("vb0="):
                        if "resourcefaceanimated" not in l:
                            # 탭(들여쓰기) 유지
                            indent = line[:len(line) - len(line.lstrip())]
                            out_lines.append(f"{indent}run = CustomShaderFaceAnimation\n")
                            out_lines.append(f"{indent}vb0 = ResourceFaceAnimated\n")
                            continue # 원래 vb0 라인 건너뜀
                    # 중복 방지
                    if l.startswith("run ") and "customshaderfaceanimation" in l:
                        continue
                        
            out_lines.append(line)
            
        # 3. 하단에 Custom Shader 파트 텍스트 주입
        if not has_custom_shader:
            # Dispatch 횟수 계산 (커스텀 버텍스 수)
            custom_size = os.path.getsize(os.path.join(os.path.dirname(ini_path), custom_buf_name))
            v_count = custom_size // 40
            dispatch_groups = math.ceil(v_count / 64.0)
            
            custom_resource_name = "ResourceFaceExpressionBase" # 기본값
            # 실제 ini의 리소스 이름을 쓰거나 복사본을 쓰거나
            # 쉽게 하기 위해 ini에서 찾은 리소스 이름을 쓴다.
            # 하지만 위에서 찾은 리소스가 custom_resource_name 이 됨
            
            # 우리는 이미 custom_buf_name을 알고 있으므로, Resource를 하나 새로 파거나,
            # 기존 리소스를 활용할 수 있다.
            # 가장 안전한 방법: 우리가 직접 새 Resource 블록을 만들고 거길 가리킨다!
            
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

class XXMI_OT_file_picker(bpy.types.Operator):
    bl_idname = "object.xxmi_file_picker"
    bl_label = "파일 선택"
    
    filepath: bpy.props.StringProperty(subtype="FILE_PATH")
    filter_glob: bpy.props.StringProperty(default="", options={'HIDDEN'})
    prop_name: bpy.props.StringProperty(options={'HIDDEN'})
    
    def execute(self, context):
        setattr(context.scene.xxmi_face_anim_props, self.prop_name, self.filepath)
        return {'FINISHED'}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

classes = (
    XXMI_OT_export_face_animation,
    XXMI_OT_file_picker,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
