import json
import pandas as pd
from datetime import datetime, timedelta
import webbrowser
import os
from typing import Tuple

# vessel_specs.json에서 화항선별 운항 사이클 기간 데이터 로드
def load_vessel_cycle_data() -> dict:
    """vessel_specs.json에서 화항선별 사이클 데이터 로드"""
    vessel_specs_file = os.path.join(os.path.dirname(__file__), "vessel_specs.json")
    if os.path.exists(vessel_specs_file):
        try:
            with open(vessel_specs_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            cycle_data = {}
            for vessel in data.get("vessels", []):
                vessel_id = int(vessel["id"])
                phases = vessel.get("cycle_phases", [3, 3, 3, 3])  # 기본값
                cycle_data[vessel_id] = tuple(phases)
            if cycle_data:
                return cycle_data
        except Exception as e:
            print(f"[ERROR] vessel_specs.json에서 사이클 데이터 로드 실패: {e}")
            raise ValueError("vessel_specs.json 파일이 필요합니다. 파일을 확인해주세요.")
    
    raise ValueError("vessel_specs.json 파일을 찾을 수 없습니다.")

VESSEL_PHASE_DUR = load_vessel_cycle_data()

class VoyageScheduleVisualizer:
    def __init__(self, json_file_path: str):
        self.json_file_path = json_file_path
        self.voyage_data = None
        self.schedule_df = None
        self.assignment_info = None

    def load_and_prepare_data(self):
        """JSON 데이터 로드 및 간트 차트용 데이터 준비"""
        try:
            with open(self.json_file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.voyage_data = data.get('voyage_assignments', {})
            self.assignment_info = data.get('assignment_info', {})
            print(f"데이터 로드 완료: {len(self.voyage_data)}개 항차")
            
            # 디버깅: 첫 번째 항차 키 확인
            if self.voyage_data:
                first_key = list(self.voyage_data.keys())[0]
                print(f"첫 번째 항차 키 예시: {first_key}")
            
            return True
        except Exception as e:
            print(f"데이터 로드 실패: {str(e)}")
            return False

    def generate_html_dashboard(self, output_file='dashboard_report_fixed.html'):
        """Canvas 기반 간트 차트로 HTML 대시보드 생성"""
        if not self.load_and_prepare_data(): 
            return

        total_voyages = len(self.voyage_data)
        total_blocks = sum(len(b) for b in self.voyage_data.values())
        vessel_names = set()
        for voyage_id in self.voyage_data.keys():
            vessel_names.add(voyage_id.split('_')[0])
        vessel_count = len(vessel_names)
        
        # JSON 데이터를 JavaScript에 전달
        voyage_json = json.dumps(self.voyage_data, ensure_ascii=False)
        assignment_info_json = json.dumps(self.assignment_info, ensure_ascii=False)

        # NOTE: f-string 안의 CSS와 JS에서 사용하는 중괄호 '{}'를 '{{}}'로 이스케이프 처리하여 Python의 문자열 포맷팅과 충돌하지 않도록 수정했습니다.
        html_template = f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>화항선 운항 스케줄 대시보드</title>
  <style>
    :root {{
      --cell-w: 40px;
      --cell-h: 28px;
      --hdr-h: 72px;
      --left-w: 120px;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin:0; padding:16px; font-family: 'Malgun Gothic', Arial, sans-serif;
      background:#fafafa; color:#222;
      display:flex; flex-direction:column; gap:16px;
    }}
    .row {{
      width:100%;
    }}
    .row.chart-row {{
      flex:1; min-height:500px;
    }}
    .card {{
      background:#fff; border:1px solid #e5e7eb; border-radius:14px; padding:14px; box-shadow:0 2px 6px rgba(0,0,0,.05);
    }}
    .card h2 {{ margin:0 0 8px 0; font-size:16px; }}
    .stats {{ display: flex; justify-content: space-around; margin: 12px 0; }}
    .stat-box {{ text-align: center; }}
    .stat-value {{ font-size: 20px; font-weight: bold; }}
    .stat-label {{ font-size: 12px; color: #666; }}
    #info {{ font-size:13px; line-height:1.5; white-space:pre-line; }}
    #blocksList {{ max-height:200px; overflow:auto; border:1px solid #eee; border-radius:10px; padding:8px; font-size:12px; background:#fbfbfb; }}
    #placementImage {{ max-width:100%; height:auto; border:1px solid #eee; border-radius:8px; margin-top:8px; }}
    .detail-section {{ margin-bottom:12px; }}
    .detail-section h3 {{ margin:0 0 6px 0; font-size:14px; color:#374151; }}
    .clickable-detail {{ cursor:pointer; user-select:none; }}
    .clickable-detail:hover {{ background:#f9fafb; }}
    .detail-content {{ display:none; padding-top:8px; }}
    .detail-content.expanded {{ display:block; }}
    .muted {{ color:#6b7280; }}
    .divider {{ height:1px; background:#eee; margin:8px 0; }}
    #container {{
      position:relative;
      overflow:auto;
      background:#fff;
      border:1px solid #e5e7eb;
      border-radius:14px;
      height: 500px;
      cursor: grab;
      will-change: scroll-position;
    }}
    #container.dragging {{ cursor:grabbing; }}
    canvas {{ display:block; }}
    .leftStrip {{
      position:absolute; left:0; top:0; width:var(--left-w); height:100%;
      background:linear-gradient(90deg, #fafafa, #fff);
      border-right:1px solid #e5e7eb;
      pointer-events:none;
      z-index: 10;
    }}
    #legend {{ display:flex; flex-wrap:wrap; gap:6px; margin-top:10px; }}
    #legend .chip {{ display:flex; align-items:center; gap:6px; padding:4px 8px; border:1px solid #eee; border-radius:999px; font-size:12px; }}
    #legend .sw {{ width:14px; height:10px; border-radius:3px; border:1px solid #ddd; }}
    .debug-info {{
      position: fixed;
      bottom: 10px;
      right: 10px;
      background: rgba(0,0,0,0.8);
      color: white;
      padding: 10px;
      border-radius: 5px;
      font-size: 12px;
      font-family: monospace;
      display: none;
      z-index: 1000;
    }}
    .debug-info.show {{ display: block; }}
    .vessel-toggles, .voyage-toggles {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin: 12px 0;
    }}
    .toggle-btn {{
      padding: 8px 16px;
      border: 2px solid #e5e7eb;
      border-radius: 8px;
      background: #fff;
      cursor: pointer;
      font-size: 14px;
      font-weight: 500;
      transition: all 0.2s ease;
      user-select: none;
    }}
    .toggle-btn:hover {{
      border-color: #d1d5db;
      background: #f9fafb;
    }}
    .toggle-btn.active {{
      border-color: #4f46e5;
      background: #4f46e5;
      color: white;
    }}
    .voyage-btn {{
      font-size: 12px;
      padding: 6px 12px;
    }}
    .voyage-btn.active {{
      border-color: #16a34a;
      background: #16a34a;
    }}
  </style>
</head>
<body>
  <div class="row">
    <div class="card">
      <h2>운항 통계</h2>
      <div class="stats">
        <div class="stat-box"><div class="stat-value">{total_voyages}</div><div class="stat-label">총 항차 수</div></div>
        <div class="stat-box"><div class="stat-value">{total_blocks}</div><div class="stat-label">총 블록 수</div></div>
        <div class="stat-box"><div class="stat-value">{vessel_count}</div><div class="stat-label">운항 화항선 수</div></div>
      </div>
    </div>
  </div>

  <div class="row chart-row">
    <div class="card" style="flex:1; display:flex; flex-direction:column;">
      <div id="container" style="flex:1;">
        <div class="leftStrip"></div>
        <canvas id="gantt"></canvas>
      </div>
      <div id="legend"></div>
    </div>
  </div>

  <!-- 자항선 토글 섹션 -->
  <div class="row">
    <div class="card">
      <h2>자항선 선택</h2>
      <div id="vesselToggles" class="vessel-toggles">
        <!-- 자항선 토글 버튼들이 여기에 생성됩니다 -->
      </div>
    </div>
  </div>

  <!-- 항차 토글 섹션 -->
  <div class="row" id="voyageTogglesSection" style="display:none;">
    <div class="card">
      <h2 id="selectedVesselTitle">선택된 자항선의 항차</h2>
      <div id="voyageToggles" class="voyage-toggles">
        <!-- 항차 토글 버튼들이 여기에 생성됩니다 -->
      </div>
    </div>
  </div>

  <!-- 항차 상세 정보 섹션 -->
  <div class="row" id="voyageDetailSection" style="display:none;">
    <div class="card">
      <div class="detail-section clickable-detail" onclick="toggleDetail('voyageDetail')">
        <h2>항차 상세 ▼</h2>
      </div>
      <div id="voyageDetail" class="detail-content expanded">
        <div id="info" class="muted">항차를 선택하면 상세가 여기에 표시됩니다.</div>
        <div class="divider"></div>
        <div id="blocksList"></div>
        <div id="placementImageContainer" style="display:none;">
          <div class="divider"></div>
          <h3>배치 시각화</h3>
          <img id="placementImage" alt="배치 시각화" />
        </div>
      </div>
    </div>
  </div>

  <div id="debugInfo" class="debug-info"></div>

  <script>
    const DATA = {{
      voyage_assignments: {voyage_json},
      assignment_info: {assignment_info_json}
    }};
    
    let voyageBoxes = [];
    let canvas, ctx, container;
    let hoveredBox = null;
    let DEBUG_MODE = false;
    
    const CELL_W = 40;
    const CELL_H = 28;
    const HDR_H = 72;
    const LEFT_W = 120;

    const vesselOrder = ['자항선1','자항선2','자항선3','자항선4','자항선5'];
    const colors = {{
      '자항선1': '#4F46E5',
      '자항선2': '#16A34A',
      '자항선3': '#DC2626',
      '자항선4': '#0891B2',
      '자항선5': '#A855F7'
    }};

    function parseDate(str) {{
      if(/^\\d{{4}}-\\d{{2}}-\\d{{2}}$/.test(str)) {{
        return new Date(str + 'T00:00:00.000Z');
      }}
      return new Date(str);
    }}
    
    function formatISO(d) {{ 
      return d.toISOString().slice(0,10); 
    }}
    
    function daysDiff(a,b) {{ 
      return Math.round((b - a) / 86400000); 
    }}

    function buildVoyageRanges(json) {{
      console.log('Building voyage ranges...');
      const ranges = {{}};
      const voyageAssignments = json?.voyage_assignments || {{}};
      
      // 직접 voyage_assignments의 키에서 날짜 정보 추출
      for(const voyageKey of Object.keys(voyageAssignments)) {{
        
        // voyageKey 형식: "자항선1_2024-05-21_2024-06-01"
        const parts = voyageKey.split('_');
        if(parts.length >= 3) {{
          const vessel = parts[0];
          const startDate = parseDate(parts[1]);
          const endDate = parseDate(parts[2]);
          
          ranges[voyageKey] = {{ 
            start: startDate, 
            end: endDate, 
            vessel: vessel 
          }};
        }}
      }}
      
      console.log('Total ranges built:', Object.keys(ranges).length);
      return ranges;
    }}

    function drawChart() {{
      console.log('Starting drawChart...');
      const gantt = document.getElementById('gantt');
      canvas = gantt; 
      ctx = gantt.getContext('2d'); 
      container = document.getElementById('container');

      const ranges = buildVoyageRanges(DATA);
      const all = Object.values(ranges);
      if(all.length === 0) {{
        console.error('No voyage ranges found!');
        return;
      }}
      
      const minStart = new Date(Math.min(...all.map(r => r.start.getTime())));
      const maxEnd   = new Date(Math.max(...all.map(r => r.end.getTime())));

      const chartStart = new Date(minStart); 
      chartStart.setDate(chartStart.getDate()-3);
      const chartEnd   = new Date(maxEnd);   
      chartEnd.setDate(chartEnd.getDate()+3);
      const totalDays  = daysDiff(chartStart, chartEnd) + 1;

      const rows = vesselOrder.length;
      canvas.width  = LEFT_W + totalDays * CELL_W + 2;
      canvas.height = HDR_H + rows * CELL_H + 1;

      // 배경 그리기
      ctx.fillStyle = '#fff'; 
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      // 헤더 그리기
      drawHeader(chartStart, totalDays);

      // 선박 이름 및 그리드 라인
      ctx.font = '12px Arial'; 
      ctx.textBaseline = 'middle'; 
      ctx.fillStyle = '#111827';
      
      voyageBoxes = [];
      
      vesselOrder.forEach((vessel, idx) => {{
        const y = HDR_H + idx * CELL_H;
        ctx.strokeStyle = '#e5e7eb';
        ctx.beginPath(); 
        ctx.moveTo(0, y); 
        ctx.lineTo(canvas.width, y); 
        ctx.stroke();
        ctx.fillStyle = '#111827';
        ctx.fillText(vessel, 10, y + CELL_H/2);
      }});
      
      // 마지막 그리드 라인
      ctx.strokeStyle = '#e5e7eb'; 
      ctx.beginPath();
      ctx.moveTo(0, HDR_H + rows * CELL_H); 
      ctx.lineTo(canvas.width, HDR_H + rows * CELL_H); 
      ctx.stroke();

      // 항차별로 그룹화
      const perVessel = DATA?.voyage_assignments || {{}};
      const voyagesByVessel = {{}};
      Object.keys(perVessel).forEach(vid => {{
        const vessel = vid.split('_')[0];
        if (!voyagesByVessel[vessel]) voyagesByVessel[vessel] = [];
        voyagesByVessel[vessel].push(vid);
      }});

      // 항차 박스 그리기
      vesselOrder.forEach((vessel, idx) => {{
        const list = voyagesByVessel[vessel] || [];
        const yTop = HDR_H + idx * CELL_H + 2;
                
        for(const vid of list) {{
          const r = ranges[vid];
          if(!r) {{
            console.warn('No range found for voyage:', vid);
            continue;
          }}
          
          const x = LEFT_W + daysDiff(chartStart, r.start) * CELL_W;
          const w = (daysDiff(r.start, r.end) + 1) * CELL_W;

          // 박스 그리기
          ctx.fillStyle = colors[vessel] || '#888';
          ctx.fillRect(x + 1, yTop, w - 2, CELL_H - 4);
          ctx.strokeStyle = '#111827'; 
          ctx.strokeRect(x + 0.5, yTop - 0.5, w - 1, CELL_H - 3);

          // 블록 개수 표시
          const blocks = (DATA.voyage_assignments || {{}})[vid] || [];
          const label = `${{blocks.length}}개`;
          ctx.fillStyle = '#fff'; 
          ctx.font = 'bold 12px Arial';
          const tw = ctx.measureText(label).width;
          if(tw < w - 8) {{
            ctx.fillText(label, x + (w - tw)/2, yTop + (CELL_H - 4)/2 + 1);
          }}

          // 클릭 영역 저장
          const boxInfo = {{ 
            x: x + 1,
            y: yTop,
            w: w - 2,
            h: CELL_H - 4,
            vessel, 
            vid, 
            start: r.start, 
            end: r.end, 
            blocks 
          }};
          voyageBoxes.push(boxInfo);
        }}
      }});

      // 범례 생성
      const leg = document.getElementById('legend');
      leg.innerHTML = '';
      vesselOrder.forEach(v => {{
        const chip = document.createElement('div');
        chip.className = 'chip';
        const sw = document.createElement('div'); 
        sw.className = 'sw'; 
        sw.style.background = colors[v] || '#888';
        chip.appendChild(sw); 
        chip.append(v);
        leg.appendChild(chip);
      }});

      container.scrollLeft = 0;
    }}

    function drawHeader(chartStart, totalDays) {{
      const dTmp = new Date(chartStart);
      const canvasW = LEFT_W + totalDays * CELL_W;
      const canvasH = HDR_H;

      const c = ctx;
      
      // 헤더 배경
      c.fillStyle = '#fafafa'; 
      c.fillRect(0, 0, canvasW, canvasH);
      c.strokeStyle = '#e5e7eb'; 
      c.beginPath(); 
      c.moveTo(0, HDR_H); 
      c.lineTo(canvasW, HDR_H); 
      c.stroke();

      // 세로 그리드 라인
      for(let i = 0; i <= totalDays; i++) {{
        const x = LEFT_W + i * CELL_W;
        c.strokeStyle = '#f1f5f9';
        c.beginPath(); 
        c.moveTo(x, 0); 
        c.lineTo(x, canvas.height); 
        c.stroke();
      }}

      // 왼쪽 고정 영역
      c.fillStyle = '#fff'; 
      c.fillRect(0, 0, LEFT_W, canvasH);
      c.strokeStyle = '#e5e7eb'; 
      c.beginPath(); 
      c.moveTo(LEFT_W, 0); 
      c.lineTo(LEFT_W, canvasH); 
      c.stroke();

      // 날짜 표시
      c.textBaseline = 'alphabetic';
      let lastYear = -1, lastMonth = -1;
      
      for(let i = 0; i < totalDays; i++) {{
        const x = LEFT_W + i * CELL_W;
        const year = dTmp.getFullYear();
        const month = dTmp.getMonth() + 1;
        const day = dTmp.getDate();

        if(year !== lastYear) {{
          c.fillStyle = '#111827'; 
          c.font = 'bold 14px Arial';
          c.fillText(`${{year}}년`, x + 6, 20);
          lastYear = year; 
          lastMonth = -1;
        }}
        if(month !== lastMonth) {{
          c.fillStyle = '#374151'; 
          c.font = 'bold 12px Arial';
          c.fillText(`${{month}}월`, x + 6, 40);
          lastMonth = month;
        }}
        
        const dd = day.toString().padStart(2, '0');
        c.fillStyle = '#6b7280'; 
        c.font = '12px Arial';
        const cx = x + CELL_W/2 - c.measureText(dd[0]).width/2;
        c.fillText(dd, cx, 62);

        dTmp.setDate(dTmp.getDate() + 1);
      }}
    }}

    function toggleDetail(sectionId) {{
      const section = document.getElementById(sectionId);
      const isExpanded = section.classList.contains('expanded');
      section.classList.toggle('expanded');
      
      const header = section.previousElementSibling.querySelector('h2');
      header.textContent = header.textContent.replace(/[▼▲]/, isExpanded ? '▼' : '▲');
    }}

    function showDetail(box) {{
      const voyageKey = box.vid;
      const assignments = DATA.voyage_assignments[voyageKey] || [];
      const blockCount = assignments.length;
            
      const info = document.getElementById('info');
      info.innerHTML = `
        <strong>항차:</strong> ${{voyageKey}}<br>
        <strong>기간:</strong> ${{formatISO(box.start)}} ~ ${{formatISO(box.end)}}<br>
        <strong>블록 수:</strong> ${{blockCount}}개
      `;
      
      const blockList = document.getElementById('blocksList');
      blockList.innerHTML = assignments.map(blockId => 
        `<span class="block-tag" style="display:inline-block; background:#e5e7eb; padding:2px 6px; margin:2px; border-radius:4px; font-size:11px;">${{blockId}}</span>`
      ).join('');
      
      // 배치 이미지 표시 (경로 수정)
      const imageName = box.vid.replace('_', ' ') + '.png';
      const imagePath = `placement_results/${{imageName}}`;
      const image = document.getElementById('placementImage');
      const imageContainer = document.getElementById('placementImageContainer');
      
      imageContainer.style.display = 'block';
      image.src = imagePath;
      
      image.onerror = function() {{
        imageContainer.innerHTML = `
          <div class="divider"></div>
          <h3>배치 시각화</h3>
          <div class="error-message" style="padding:20px; text-align:center; border:1px dashed #ccc; border-radius:8px; color:#666; background:#f9f9f9;">
            <strong>이미지를 찾을 수 없습니다</strong><br>
            <code style="background:#eee; padding:2px 6px; border-radius:4px; font-size:12px;">${{imagePath}}</code>
          </div>
        `;
      }};
      
      const voyageDetail = document.getElementById('voyageDetail');
      if (!voyageDetail.classList.contains('expanded')) {{
        toggleDetail('voyageDetail');
      }}
    }}
    
    // --- START: ADDED TOGGLE FUNCTIONS ---
    function setupToggles() {{
        const vesselTogglesContainer = document.getElementById('vesselToggles');
        if (!vesselTogglesContainer) return;

        vesselTogglesContainer.innerHTML = '';
        vesselOrder.forEach(vesselName => {{
            const btn = document.createElement('button');
            btn.className = 'toggle-btn';
            btn.textContent = vesselName;
            btn.dataset.vessel = vesselName;
            btn.onclick = () => selectVessel(vesselName);
            vesselTogglesContainer.appendChild(btn);
        }});
    }}

    function selectVessel(vesselName) {{
        document.querySelectorAll('#vesselToggles .toggle-btn').forEach(btn => {{
            btn.classList.toggle('active', btn.dataset.vessel === vesselName);
        }});

        const voyageTogglesSection = document.getElementById('voyageTogglesSection');
        const voyageTogglesContainer = document.getElementById('voyageToggles');
        const selectedVesselTitle = document.getElementById('selectedVesselTitle');

        voyageTogglesContainer.innerHTML = '';

        const voyagesByVessel = {{}};
        Object.keys(DATA.voyage_assignments).forEach(vid => {{
            const vessel = vid.split('_')[0];
            if (!voyagesByVessel[vessel]) voyagesByVessel[vessel] = [];
            voyagesByVessel[vessel].push(vid);
        }});

        const voyages = voyagesByVessel[vesselName] || [];

        if (voyages.length > 0 && voyages[0] !== "없음") {{
            selectedVesselTitle.textContent = `${{vesselName}} 항차 목록`;
            voyages.forEach(voyageId => {{
                const parts = voyageId.split('_');
                if (parts.length < 3) return;
                const startDate = parts[1];
                const endDate = parts[2];

                const btn = document.createElement('button');
                btn.className = 'toggle-btn voyage-btn';
                btn.textContent = `${{startDate}} ~ ${{endDate}}`;
                btn.dataset.voyageId = voyageId;
                btn.onclick = () => showVoyageDetailFromToggle(voyageId);
                voyageTogglesContainer.appendChild(btn);
            }});
            voyageTogglesSection.style.display = 'block';
        }} else {{
            voyageTogglesSection.style.display = 'none';
        }}
        
        document.getElementById('voyageDetailSection').style.display = 'none';
    }}

    function showVoyageDetailFromToggle(voyageId) {{
        document.querySelectorAll('#voyageToggles .toggle-btn').forEach(btn => {{
            btn.classList.toggle('active', btn.dataset.voyageId === voyageId);
        }});
        
        const detailSection = document.getElementById('voyageDetailSection');
        const infoEl = document.getElementById('info');
        const blocksListEl = document.getElementById('blocksList');
        const imageContainerEl = document.getElementById('placementImageContainer');
        
        const assignments = DATA.voyage_assignments[voyageId] || [];
        const blockCount = assignments.length;
        const parts = voyageId.split('_');
        const startDate = parts[1];
        const endDate = parts[2];

        detailSection.style.display = 'block';

        infoEl.innerHTML = `
            <strong>항차:</strong> ${{voyageId}}<br>
            <strong>기간:</strong> ${{startDate}} ~ ${{endDate}}<br>
            <strong>블록 수:</strong> ${{blockCount}}개
        `;

        blocksListEl.innerHTML = assignments.map(blockId => 
            `<span class="block-tag" style="display:inline-block; background:#e5e7eb; padding:2px 6px; margin:2px; border-radius:4px; font-size:11px;">${{blockId}}</span>`
        ).join('') || '<li>실린 블록 정보가 없습니다.</li>';

        // Reset image container before loading new one
        imageContainerEl.innerHTML = `
            <div class="divider"></div>
            <h3>배치 시각화</h3>
            <img id="placementImage" alt="배치 시각화" />
        `;
        const imageEl = document.getElementById('placementImage');

        const imageName = voyageId.replace('_', ' ') + '.png';
        const imagePath = `placement_results/${{imageName}}`;
        imageContainerEl.style.display = 'block';
        imageEl.src = imagePath;
        
        imageEl.onerror = function() {{
            imageContainerEl.innerHTML = `
              <div class="divider"></div>
              <h3>배치 시각화</h3>
              <div class="error-message" style="padding:20px; text-align:center; border:1px dashed #ccc; border-radius:8px; color:#666; background:#f9f9f9;">
                <strong>이미지를 찾을 수 없습니다</strong><br>
                <code style="background:#eee; padding:2px 6px; border-radius:4px; font-size:12px;">${{imagePath}}</code>
              </div>
            `;
        }};
        
        const voyageDetailContent = document.getElementById('voyageDetail');
        if (!voyageDetailContent.classList.contains('expanded')) {{
          toggleDetail('voyageDetail');
        }}
    }}
    // --- END: ADDED TOGGLE FUNCTIONS ---

    // 개선된 hitTest 함수
    function hitTest(canvasX, canvasY) {{
      if(DEBUG_MODE) {{
        showDebugInfo(canvasX, canvasY);
      }}
      
      // 역순으로 검사 (위에 그려진 것부터)
      for(let i = voyageBoxes.length - 1; i >= 0; i--) {{
        const box = voyageBoxes[i];
        
        // 박스 경계 체크
        if(canvasX >= box.x && 
           canvasX < box.x + box.w && 
           canvasY >= box.y && 
           canvasY < box.y + box.h) {{
          
          if(DEBUG_MODE) {{
            console.log('Hit detected:', {{
              vid: box.vid,
              clickX: canvasX,
              clickY: canvasY,
              box: {{
                left: box.x,
                right: box.x + box.w,
                top: box.y,
                bottom: box.y + box.h
              }}
            }});
          }}
          
          return box;
        }}
      }}
      return null;
    }}

    // 디버그 정보 표시 함수
    function showDebugInfo(x, y) {{
      const debugDiv = document.getElementById('debugInfo');
      debugDiv.classList.add('show');
      debugDiv.innerHTML = `
        Canvas X: ${{x.toFixed(0)}}<br>
        Canvas Y: ${{y.toFixed(0)}}<br>
        Scroll Left: ${{container.scrollLeft}}<br>
        Scroll Top: ${{container.scrollTop}}
      `;
      setTimeout(() => debugDiv.classList.remove('show'), 3000);
    }}

    // Canvas 좌표로 변환하는 함수
    function getCanvasCoordinates(e) {{
      const rect = canvas.getBoundingClientRect();
      const scaleX = canvas.width / rect.width;
      const scaleY = canvas.height / rect.height;
      
      return {{
        x: (e.clientX - rect.left) * scaleX + container.scrollLeft,
        y: (e.clientY - rect.top) * scaleY + container.scrollTop
      }};
    }}

    // 이벤트 처리 설정
    (function setupInteractions() {{
      const cont = document.getElementById('container');
      let isDown = false;
      let startX = 0;
      let startY = 0;
      let scrollLeft = 0;
      let scrollTop = 0;
      let hasMoved = false;
      const DRAG_THRESHOLD = 5;
      
      cont.addEventListener('mousedown', (e) => {{
        isDown = true; 
        startX = e.clientX;
        startY = e.clientY;
        scrollLeft = cont.scrollLeft;
        scrollTop = cont.scrollTop;
        hasMoved = false;
        e.preventDefault();
      }});
      
      cont.addEventListener('mouseleave', () => {{
        isDown = false; 
        cont.classList.remove('dragging');
      }});
      
      cont.addEventListener('mouseup', () => {{
        isDown = false; 
        setTimeout(() => cont.classList.remove('dragging'), 10);
      }});
      
      cont.addEventListener('mousemove', (e) => {{
        if(!isDown) {{
          // 호버 효과를 위한 처리
          const coords = getCanvasCoordinates(e);
          const box = hitTest(coords.x, coords.y);
          
          if(box !== hoveredBox) {{
            hoveredBox = box;
            cont.style.cursor = box ? 'pointer' : 'grab';
          }}
          return;
        }}
        
        // 드래그 처리
        const moveX = Math.abs(e.clientX - startX);
        const moveY = Math.abs(e.clientY - startY);
        
        if(moveX > DRAG_THRESHOLD || moveY > DRAG_THRESHOLD) {{
          hasMoved = true;
          cont.classList.add('dragging');
          cont.style.cursor = 'grabbing';
          cont.scrollLeft = scrollLeft - (e.clientX - startX);
          cont.scrollTop = scrollTop - (e.clientY - startY);
        }}
      }});
      
      cont.addEventListener('wheel', (e) => {{
        if(e.ctrlKey) {{
          e.preventDefault();
        }}
      }}, {{passive: false}});

      // 클릭 이벤트 처리
      cont.addEventListener('click', (e) => {{
        // 드래그 중이면 클릭 무시
        if(hasMoved || cont.classList.contains('dragging')) {{
          return;
        }}
        
        // Canvas 좌표 계산
        const coords = getCanvasCoordinates(e);
        
        if(DEBUG_MODE) {{
          console.log('Click event:', {{
            clientX: e.clientX,
            clientY: e.clientY,
            canvasX: coords.x,
            canvasY: coords.y,
            scrollLeft: cont.scrollLeft,
            scrollTop: cont.scrollTop
          }});
        }}
        
        // 클릭된 박스 찾기
        const box = hitTest(coords.x, coords.y);
        if(box) {{
          showDetail(box);
        }} else {{
          if(DEBUG_MODE) {{
            console.log('No box found at:', coords.x, coords.y);
          }}
        }}
      }});
    }})();

    // 차트 그리기 및 토글 설정 실행
    drawChart();
    setupToggles();
    window.addEventListener('resize', drawChart);

    // 디버그 모드 토글 (Ctrl+D)
    document.addEventListener('keydown', (e) => {{
      if(e.ctrlKey && e.key === 'd') {{
        e.preventDefault();
        DEBUG_MODE = !DEBUG_MODE;
        console.log('Debug mode:', DEBUG_MODE);
        const debugDiv = document.getElementById('debugInfo');
        if(DEBUG_MODE) {{
          debugDiv.classList.add('show');
        }} else {{
          debugDiv.classList.remove('show');
        }}
      }}
    }});
  </script>
</body>
</html>"""

        output_dir = os.path.dirname(output_file)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html_template)
        print(f"대시보드가 '{output_file}' 파일로 저장되었습니다.")
        
        try:
            webbrowser.open(f"file://{os.path.realpath(output_file)}")
        except Exception as e:
            print(f"브라우저를 자동으로 여는 데 실패했습니다: {e}")
            print(f"   직접 파일을 열어 확인해주세요: {os.path.realpath(output_file)}")

# --- 스크립트 실행 ---
if __name__ == "__main__":
    visualizer = VoyageScheduleVisualizer(json_file_path="lv3_integrated_voyage_assignments.json")
    visualizer.generate_html_dashboard()


