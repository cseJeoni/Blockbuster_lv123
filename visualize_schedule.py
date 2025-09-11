import json
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import webbrowser
import os
from typing import Tuple

# 자항선별 운항 사이클 기간 데이터
VESSEL_PHASE_DUR = {
    1: (3, 3, 3, 3),   # 자항선1: 12일
    2: (3, 1, 3, 1),   # 자항선2: 8일
    3: (3, 3, 3, 2),   # 자항선3: 11일
    4: (3, 3, 3, 2),   # 자항선4: 11일
    5: (3, 3, 3, 2),   # 자항선5: 11일
}

# 자항선별 색상 정의
VESSEL_COLORS = {
    '자항선1': '#FF6B6B',
    '자항선2': '#4ECDC4',
    '자항선3': '#45B7D1',
    '자항선4': '#96CEB4',
    '자항선5': '#FFEAA7'
}

class VoyageScheduleVisualizer:
    def __init__(self):
        self.voyage_data = None
        self.schedule_df = None

    def load_data(self, json_file_path: str):
        """JSON 데이터 로드"""
        try:
            with open(json_file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.voyage_data = data.get('voyage_assignments', {})
            print(f"데이터 로드 완료: {len(self.voyage_data)}개 항차")
            return True
        except Exception as e:
            print(f"데이터 로드 실패: {str(e)}")
            return False

    def parse_voyage_info(self, voyage_id: str) -> Tuple[str, datetime]:
        """항차 ID에서 자항선명과 종료일 파싱"""
        parts = voyage_id.split('_')
        vessel_name = parts[0]
        end_date_str = parts[1]
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
        return vessel_name, end_date

    def calculate_start_date(self, vessel_name: str, end_date: datetime) -> datetime:
        """항차 시작일 계산"""
        vessel_num = int(vessel_name.replace('자항선', ''))
        total_cycle_days = sum(VESSEL_PHASE_DUR[vessel_num])
        start_date = end_date - timedelta(days=total_cycle_days - 1)
        return start_date

    def prepare_schedule_data(self):
        """간트 차트용 데이터 준비"""
        schedule_data = []

        for voyage_id, blocks in self.voyage_data.items():
            vessel_name, end_date = self.parse_voyage_info(voyage_id)
            start_date = self.calculate_start_date(vessel_name, end_date)

            schedule_data.append({
                'voyage_id': voyage_id,
                'vessel_name': vessel_name,
                'start_date': start_date,
                'end_date': end_date,
                'duration': (end_date - start_date).days + 1,
                'blocks': blocks,
                'block_count': len(blocks)
            })

        self.schedule_df = pd.DataFrame(schedule_data)
        self.schedule_df = self.schedule_df.sort_values(['vessel_name', 'start_date'])
        print(f"스케줄 데이터 준비 완료: {len(self.schedule_df)}개 항차")

    def create_interactive_dashboard(self):
        """인터랙티브 간트 차트 생성 (상단 차트만)"""
        if self.schedule_df is None:
            return None

        fig = go.Figure()

        vessel_names = sorted(self.schedule_df['vessel_name'].unique())

        # 자항선1이 위, 자항선5가 아래로 보이도록 y축을 뒤집을 예정
        for i, vessel_name in enumerate(vessel_names):
            vessel_data = self.schedule_df[self.schedule_df['vessel_name'] == vessel_name]
            for j, (_, row) in enumerate(vessel_data.iterrows()):
                is_first = (j == 0)
                # 직사각형 폴리곤
                xs = [row['start_date'], row['end_date'], row['end_date'], row['start_date'], row['start_date']]
                ys = [i-0.3, i-0.3, i+0.3, i+0.3, i-0.3]

                fig.add_trace(
                    go.Scatter(
                        x=xs,
                        y=ys,
                        fill='toself',
                        fillcolor=VESSEL_COLORS.get(vessel_name, '#999'),
                        line=dict(color=VESSEL_COLORS.get(vessel_name, '#999'), width=2),
                        name=vessel_name if is_first else "",
                        showlegend=is_first,
                        # 클릭 시 항차 식별을 위해 customdata에 voyage_id 넣기 (폴리곤 포인트 수만큼 반복)
                        customdata=[row['voyage_id']] * len(xs),
                        hovertemplate=(
                            f"<b>{row['voyage_id']}</b><br>"
                            f"자항선: {row['vessel_name']}<br>"
                            f"시작: {row['start_date'].strftime('%Y-%m-%d')}<br>"
                            f"종료: {row['end_date'].strftime('%Y-%m-%d')}<br>"
                            f"기간: {row['duration']}일<br>"
                            f"블록 수: {row['block_count']}<br>"
                            "<extra></extra>"
                        ),
                        mode='lines'
                    )
                )

        # Y축: 자항선 라벨 + 위에서 1 시작되도록 반전
        fig.update_yaxes(
            tickmode='array',
            tickvals=list(range(len(vessel_names))),
            ticktext=vessel_names,
            title="자항선",
            autorange='reversed'  # <= 자항선1이 맨 위
        )

        # X축: 1일 간격 모든 날짜 라벨 노출
        fig.update_xaxes(
            title="날짜",
            type='date',
            tickformat='%Y-%m-%d',
            dtick='D1',           # <= 1일 간격
            tickangle=-45,        # 가독성 향상
            ticklabelmode='instant'
        )

        # 전체 레이아웃
        fig.update_layout(
            title="자항선 운항 스케줄 간트 차트",
            height=600,
            dragmode='pan',
            hovermode='closest',
            showlegend=True,
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1
            ),
            margin=dict(l=60, r=20, t=80, b=80)
        )

        return fig

    def generate_html_report(self, output_file='vessel_schedule_dashboard.html'):
        """HTML 리포트 생성 (클릭 시 하단 패널 업데이트)"""
        if self.schedule_df is None:
            print("데이터가 준비되지 않았습니다.")
            return

        fig = self.create_interactive_dashboard()

        # 통계 정보
        total_voyages = len(self.voyage_data)
        total_blocks = sum(len(blocks) for blocks in self.voyage_data.values())
        vessel_count = len(set(voyage_id.split('_')[0] for voyage_id in self.voyage_data.keys()))
        date_range = (self.schedule_df['end_date'].max() - self.schedule_df['start_date'].min()).days

        # 항차별 상세 테이블 (고정 표)
        voyage_details_html = "<h3>항차별 상세 정보 (전체)</h3><table border='1' style='border-collapse: collapse; width: 100%;'>"
        voyage_details_html += "<tr><th>항차 ID</th><th>자항선</th><th>시작일</th><th>종료일</th><th>기간</th><th>블록 수</th><th>블록 목록</th></tr>"
        for _, row in self.schedule_df.iterrows():
            blocks = self.voyage_data[row['voyage_id']]
            blocks_str = ', '.join(blocks[:10])
            if len(blocks) > 10:
                blocks_str += f" ... (총 {len(blocks)}개)"
            voyage_details_html += f"""
            <tr>
                <td><strong>{row['voyage_id']}</strong></td>
                <td>{row['vessel_name']}</td>
                <td>{row['start_date'].strftime('%Y-%m-%d')}</td>
                <td>{row['end_date'].strftime('%Y-%m-%d')}</td>
                <td>{row['duration']}일</td>
                <td>{row['block_count']}</td>
                <td>{blocks_str}</td>
            </tr>
            """
        voyage_details_html += "</table>"

        # 차트 HTML (div_id 고정)
        chart_html = fig.to_html(include_plotlyjs=True, div_id="gantt-chart")

        # 블록 목록 패널 (클릭 시 갱신)
        # voyage_data를 그대로 JS로 전달해서 즉시 렌더
        voyage_json = json.dumps(self.voyage_data, ensure_ascii=False)

        html_template = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>자항선 운항 스케줄 대시보드</title>
            <meta charset="utf-8">
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .stats {{ display: flex; flex-wrap: wrap; gap: 12px; margin: 16px 0; }}
                .stat-box {{ flex: 1 1 180px; text-align: center; padding: 10px; border: 1px solid #ddd; border-radius: 8px; }}
                .stat-value {{ font-size: 24px; font-weight: 700; color: #333; }}
                .stat-label {{ font-size: 13px; color: #666; }}
                #detail-wrap {{ margin-top: 18px; padding: 12px 14px; border: 1px solid #e5e5e5; border-radius: 8px; background: #fafafa; }}
                #voyage-detail h3 {{ margin: 0 0 10px 0; }}
                #blocks {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 6px; }}
                .chip {{ padding: 6px 8px; border-radius: 6px; background: #fff; border: 1px solid #ddd; font-size: 12px; }}
                table {{ margin: 20px 0; }}
                th {{ background-color: #f5f5f5; padding: 8px; }}
                td {{ padding: 8px; }}
            </style>
        </head>
        <body>
            <h1>자항선 운항 스케줄 대시보드</h1>

            <div class="stats">
                <div class="stat-box">
                    <div class="stat-value">{total_voyages}</div>
                    <div class="stat-label">총 항차 수</div>
                </div>
                <div class="stat-box">
                    <div class="stat-value">{total_blocks}</div>
                    <div class="stat-label">총 블록 수</div>
                </div>
                <div class="stat-box">
                    <div class="stat-value">{vessel_count}</div>
                    <div class="stat-label">운항 자항선 수</div>
                </div>
                <div class="stat-box">
                    <div class="stat-value">{date_range}</div>
                    <div class="stat-label">전체 스케줄 기간 (일)</div>
                </div>
            </div>

            {chart_html}

            <div id="detail-wrap">
                <div id="voyage-detail">
                    <h3>항차 상세 정보</h3>
                    <p style="color:#666;">위 차트의 막대를 클릭하면 해당 항차의 블록 목록이 여기에 표시됩니다.</p>
                </div>
            </div>

            {voyage_details_html}

            <script>
                const voyageData = {voyage_json};
                const gd = document.getElementById("gantt-chart");

                function renderVoyageDetail(voyageId) {{
                    const blocks = voyageData[voyageId] || [];
                    const count = blocks.length;
                    const rows = blocks.map(b => '<span class="chip">'+ b +'</span>').join('');
                    const html = `
                        <h3>항차 상세 정보 - <span style="color:#333;">${{voyageId}}</span></h3>
                        <p><strong>블록 수:</strong> ${{count}}개</p>
                        <div id="blocks">${{rows}}</div>
                    `;
                    document.getElementById("voyage-detail").innerHTML = html;
                    // 상세로 스크롤 살짝 이동
                    document.getElementById("detail-wrap").scrollIntoView({{behavior: 'smooth', block: 'start'}});
                }}

                // Plotly 클릭 이벤트 연결
                if (gd && gd.on) {{
                    gd.on('plotly_click', function(ev) {{
                        try {{
                            // 첫 포인트의 customdata에 voyage_id가 들어있음
                            const pt = ev.points && ev.points[0];
                            const voyageId = pt && pt.customdata;
                            if (voyageId) renderVoyageDetail(voyageId);
                        }} catch (e) {{
                            console.warn('click handler error', e);
                        }}
                    }});
                }}
            </script>
        </body>
        </html>
        """

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html_template)

        print(f"대시보드가 '{output_file}' 파일로 저장되었습니다.")
        return output_file

def main():
    print("=== 자항선 운항 스케줄 시각화 도구 ===")
    json_file_path = "lv3_integrated_voyage_assignments.json"

    if not os.path.exists(json_file_path):
        print(f"파일을 찾을 수 없습니다: {json_file_path}")
        print("현재 디렉토리에 'lv3_integrated_voyage_assignments.json' 파일이 있는지 확인하세요.")
        return

    visualizer = VoyageScheduleVisualizer()
    if not visualizer.load_data(json_file_path):
        return

    visualizer.prepare_schedule_data()
    output_file = visualizer.generate_html_report()

    if output_file and os.path.exists(output_file):
        file_path = os.path.abspath(output_file)
        print(f"브라우저에서 대시보드를 여는 중... ({file_path})")
        webbrowser.open(f"file://{file_path}")

    print("\n프로그램을 종료하려면 아무 키나 누르세요...")
    input()

if __name__ == "__main__":
    main()
