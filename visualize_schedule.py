import json
from datetime import datetime, timedelta
import plotly.graph_objects as go
import pandas as pd

## --- VESSEL_PHASE_DUR 변수 ---
# LV3 스케줄러에서 사용하는 선박별 운항 사이클 기간 (일)
# (이동, 선적, 이동, 하역)
VESSEL_PHASE_DUR = {
    1: (3, 3, 3, 3),   # 자항선1: 12일
    2: (3, 1, 3, 1),   # 자항선2: 8일
    3: (3, 3, 3, 2),   # 자항선3: 11일
    4: (3, 3, 3, 2),   # 자항선4: 11일
    5: (3, 3, 3, 2),   # 자항선5: 11일
}

def cycle_len(vessel_id: int) -> int:
    """선박 ID에 따른 총 운항 사이클 길이를 반환합니다."""
    return sum(VESSEL_PHASE_DUR[vessel_id])

def create_gantt_chart_plotly(json_file_path: str, output_html_path: str):
    """Plotly Graph Objects를 사용하여 정밀한 인터랙티브 간트 차트를 생성합니다."""
    
    with open(json_file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    voyage_assignments = data.get("voyage_assignments", {})
    assignment_info = data.get("assignment_info", {})
    
    tasks = []
    for voyage_id, blocks in voyage_assignments.items():
        if not blocks:
            continue
        parts = voyage_id.split('_')
        vessel_name, end_date_str = parts[0], parts[1]
        vessel_id = int(vessel_name.replace("자항선", ""))
        end_date = datetime.strptime(end_date_str, "%Y-%m-%d")
        start_date = end_date - timedelta(days=cycle_len(vessel_id) - 1)
        tasks.append(dict(
            Vessel=vessel_name,
            Start=start_date,
            Finish=end_date,
            Blocks=blocks,
            VoyageID=voyage_id
        ))
        
    if not tasks:
        print("시각화할 항차 데이터가 없습니다.")
        return
        
    df = pd.DataFrame(tasks)
    
    # 자항선 번호 순서대로 정렬
    vessels = sorted(df['Vessel'].unique(), key=lambda x: int(x.replace("자항선", "")))
    
    # --- [수정]: figure_factory 대신 graph_objects로 차트 직접 생성 ---
    fig = go.Figure()
    
    colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd'] # Plotly 기본 색상
    vessel_colors = {vessel: colors[i % len(colors)] for i, vessel in enumerate(vessels)}

    for vessel in vessels:
        df_vessel = df[df['Vessel'] == vessel]
        
        hover_texts = []
        for _, row in df_vessel.iterrows():
            blocks_str = "<br>".join(row['Blocks'])
            hover_text = f"<b>{row['VoyageID']}</b><br>총 {len(row['Blocks'])}개 블록:<br>{blocks_str}"
            hover_texts.append(hover_text)
            
        fig.add_trace(go.Bar(
            y=df_vessel['Vessel'],
            x=df_vessel['Finish'] - df_vessel['Start'], # 기간(Timedelta)
            base=df_vessel['Start'],                  # 시작 날짜
            orientation='h',
            name=vessel,
            marker_color=vessel_colors[vessel],
            text=df_vessel.apply(lambda row: len(row['Blocks']), axis=1), # 막대 위에 블록 개수 표시
            textposition='inside',
            insidetextanchor='middle',
            customdata=hover_texts,
            hovertemplate='%{customdata}<extra></extra>' # extra: 추가 정보(trace 이름) 숨기기
        ))

    # 초기 날짜 범위 설정
    min_start_date = df['Start'].min()
    initial_start = min_start_date - timedelta(days=10)
    initial_end = initial_start + timedelta(days=60)

    fig.update_layout(
        title=f"자항선 최종 운항 스케줄 (총 비용: {assignment_info.get('total_cost_krw', 'N/A')})",
        xaxis_title="날짜",
        yaxis_title="자항선",
        font=dict(size=12),
        plot_bgcolor='rgba(240, 240, 240, 0.95)',
        yaxis=dict(categoryorder='array', categoryarray=vessels[::-1]), # 자항선1이 위로 오도록 역순 정렬
        xaxis=dict(
            type='date',
            range=[initial_start.strftime('%Y-%m-%d'), initial_end.strftime('%Y-%m-%d')],
            rangeselector=dict(
                buttons=list([
                    dict(count=1, label="1m", step="month", stepmode="backward"),
                    dict(count=3, label="3m", step="month", stepmode="backward"),
                    dict(count=6, label="6m", step="month", stepmode="backward"),
                    dict(step="all")
                ])
            ),
            rangeslider=dict(visible=True)
        ),
        legend_title="범례",
        barmode='stack' # 막대가 겹치지 않도록 스택 모드 설정
    )

    fig.write_html(output_html_path)
    print(f"✅ 정밀 간트 차트가 '{output_html_path}' 파일로 저장되었습니다.")

# --- 실행 ---
if __name__ == "__main__":
    create_gantt_chart_plotly(
        json_file_path="lv3_integrated_voyage_assignments.json",
        output_html_path="voyage_gantt_chart_final.html"
    )