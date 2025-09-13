import json
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import webbrowser
import os
from typing import Tuple, Dict, List

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
            self.block_assignments = data.get('block_assignments', {})
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

    def get_block_deadlines(self) -> Dict[str, str]:
        """블록별 납기일 정보 로드"""
        try:
            with open("data/block_deadline_7.csv", 'r', encoding='utf-8') as f:
                import csv
                reader = csv.DictReader(f)
                deadlines = {}
                for row in reader:
                    deadline = row["deadline"].strip()
                    if len(deadline) == 6:  # YYMMDD 형식
                        deadline = f"20{deadline[:2]}-{deadline[2:4]}-{deadline[4:]}"
                    deadlines[row["block_id"]] = deadline
                return deadlines
        except:
            return {}

    def create_interactive_dashboard(self):
        """인터랙티브 간트 차트 생성 (개선된 날짜 표시)"""
        if self.schedule_df is None:
            return None

        # 블록 납기일 정보 로드
        block_deadlines = self.get_block_deadlines()

        fig = go.Figure()
        vessel_names = sorted(self.schedule_df['vessel_name'].unique())

        # 날짜 범위 계산
        min_date = self.schedule_df['start_date'].min()
        max_date = self.schedule_df['end_date'].max()
        
        # 간트 차트 생성
        for i, vessel_name in enumerate(vessel_names):
            vessel_data = self.schedule_df[self.schedule_df['vessel_name'] == vessel_name]
            for j, (_, row) in enumerate(vessel_data.iterrows()):
                is_first = (j == 0)
                
                # 블록 정보 준비 (납기일 포함)
                blocks = self.voyage_data[row['voyage_id']]
                block_info_list = []
                for block_id in blocks:
                    deadline = block_deadlines.get(block_id, "미확인")
                    block_info_list.append(f"{block_id} ({deadline})")
                
                blocks_text = "<br>".join(block_info_list[:10])
                if len(blocks) > 10:
                    blocks_text += f"<br>... 외 {len(blocks)-10}개"

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
                        customdata=[row['voyage_id']] * len(xs),
                        hovertemplate=(
                            f"<b>{row['start_date'].strftime('%Y-%m-%d')}_{row['end_date'].strftime('%Y-%m-%d')}</b><br>"
                            f"실린 블록 개수: {row['block_count']}<br>"
                            f"실린 블록 ID (납기일):<br>{blocks_text}<br>"
                            "<extra></extra>"
                        ),
                        mode='lines'
                    )
                )

        # Y축 설정
        fig.update_yaxes(
            tickmode='array',
            tickvals=list(range(len(vessel_names))),
            ticktext=vessel_names,
            title="자항선",
            autorange='reversed'
        )

        # X축 설정 - 개선된 날짜 표시
        fig.update_xaxes(
            title="",
            type='date',
            tickformat='%d',  # 일만 표시
            dtick='D1',
            tickangle=0,
            ticklabelmode='instant',
            showgrid=True,
            gridwidth=1,
            gridcolor='lightgray'
        )

        # 레이아웃 설정
        fig.update_layout(
            title="자항선 운항 스케줄 간트 차트",
            height=700,
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
            margin=dict(l=60, r=20, t=150, b=80),  # 상단 여백 증가
            xaxis=dict(
                fixedrange=False,  # 수평 스크롤 허용
                rangeslider=dict(visible=False),  # 범위 슬라이더 비활성화
                # 초기 표시 범위를 제한하여 스크롤 성능 향상
                range=[min_date, min_date + timedelta(days=60)]
            ),
            yaxis=dict(
                fixedrange=True  # 수직 스크롤 비활성화
            ),
            # 드래그 성능 최적화
            uirevision='constant',  # UI 상태 유지
            transition={'duration': 0}  # 애니메이션 비활성화로 성능 향상
        )

        # 년도, 월, 일 표시를 위한 추가 annotation 생성
        self.add_date_annotations(fig, min_date, max_date)

        return fig

    def add_date_annotations(self, fig, min_date: datetime, max_date: datetime):
        """년도, 월, 일 표시를 위한 annotation 추가"""
        current_date = min_date
        
        # 년도 표시
        current_year = None
        year_start = None
        
        # 월 표시
        current_month = None
        month_start = None
        
        while current_date <= max_date:
            # 년도 변경 감지
            if current_year != current_date.year:
                if current_year is not None:
                    # 이전 년도 표시
                    year_mid = year_start + (current_date - timedelta(days=1) - year_start) / 2
                    fig.add_annotation(
                        x=year_mid,
                        y=len(self.schedule_df['vessel_name'].unique()) + 0.8,
                        text=str(current_year),
                        showarrow=False,
                        font=dict(size=14, color="black"),
                        bgcolor="white",
                        bordercolor="black",
                        borderwidth=1
                    )
                current_year = current_date.year
                year_start = current_date
            
            # 월 변경 감지
            if current_month != current_date.month:
                if current_month is not None:
                    # 이전 월 표시
                    month_mid = month_start + (current_date - timedelta(days=1) - month_start) / 2
                    fig.add_annotation(
                        x=month_mid,
                        y=len(self.schedule_df['vessel_name'].unique()) + 0.4,
                        text=f"{current_month}월",
                        showarrow=False,
                        font=dict(size=12, color="darkblue"),
                        bgcolor="lightblue",
                        bordercolor="blue",
                        borderwidth=1
                    )
                current_month = current_date.month
                month_start = current_date
            
            current_date += timedelta(days=1)
        
        # 마지막 년도와 월 표시
        if current_year is not None:
            year_mid = year_start + (max_date - year_start) / 2
            fig.add_annotation(
                x=year_mid,
                y=len(self.schedule_df['vessel_name'].unique()) + 0.8,
                text=str(current_year),
                showarrow=False,
                font=dict(size=14, color="black"),
                bgcolor="white",
                bordercolor="black",
                borderwidth=1
            )
        
        if current_month is not None:
            month_mid = month_start + (max_date - month_start) / 2
            fig.add_annotation(
                x=month_mid,
                y=len(self.schedule_df['vessel_name'].unique()) + 0.4,
                text=f"{current_month}월",
                showarrow=False,
                font=dict(size=12, color="darkblue"),
                bgcolor="lightblue",
                bordercolor="blue",
                borderwidth=1
            )

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

        # 통계 정보 계산
        vessel_names = sorted(self.schedule_df['vessel_name'].unique())
        total_days = (self.schedule_df['end_date'].max() - self.schedule_df['start_date'].min()).days
        
        # 날짜 범위 계산
        min_date = self.schedule_df['start_date'].min()
        max_date = self.schedule_df['end_date'].max()
        
        # 블록 납기일 정보 로드
        block_deadlines = self.get_block_deadlines()

        # Plotly 차트 데이터를 JSON 직렬화 가능한 형태로 변환
        chart_data = []
        chart_layout = {
            'title': '자항선 운항 스케줄 간트 차트',
            'height': 700,
            'dragmode': 'pan',
            'hovermode': 'closest',
            'showlegend': True,
            'legend': {
                'orientation': 'h',
                'yanchor': 'bottom',
                'y': 1.02,
                'xanchor': 'right',
                'x': 1
            },
            'margin': {'l': 60, 'r': 20, 't': 200, 'b': 80},  # 상단 여백 더 증가
            'xaxis': {
                'title': '',
                'type': 'date',
                'tickformat': '',  # 빈 문자열로 설정하여 기본 틱 숨김
                'dtick': 'D1',
                'tickangle': 0,
                'ticklabelmode': 'instant',
                'showgrid': True,
                'gridwidth': 1,
                'gridcolor': 'lightgray',
                'fixedrange': False,
                'rangeslider': {'visible': False},
                'range': [min_date.strftime('%Y-%m-%d'), (min_date + timedelta(days=30)).strftime('%Y-%m-%d')],  # 30일로 줄여서 확대
                'showticklabels': False  # X축 기본 라벨 숨김
            },
            'yaxis': {
                'tickmode': 'array',
                'tickvals': list(range(len(vessel_names))),
                'ticktext': vessel_names,
                'title': '자항선',
                'autorange': 'reversed',
                'fixedrange': True
            },
            'uirevision': 'constant',
            'transition': {'duration': 0},
            'scrollZoom': False  # 마우스 휠 줌 비활성화
        }

        # 간트 차트 데이터 생성
        for i, vessel_name in enumerate(vessel_names):
            vessel_data = self.schedule_df[self.schedule_df['vessel_name'] == vessel_name]
            for j, (_, row) in enumerate(vessel_data.iterrows()):
                is_first = (j == 0)
                
                # 블록 정보 준비 (납기일 포함)
                blocks = self.voyage_data[row['voyage_id']]
                block_info_list = []
                for block_id in blocks:
                    deadline = block_deadlines.get(block_id, "미확인")
                    block_info_list.append(f"{block_id} ({deadline})")
                
                blocks_text = "<br>".join(block_info_list[:10])
                if len(blocks) > 10:
                    blocks_text += f"<br>... 외 {len(blocks)-10}개"

                # 직사각형 폴리곤 데이터
                xs = [
                    row['start_date'].strftime('%Y-%m-%d'), 
                    row['end_date'].strftime('%Y-%m-%d'), 
                    row['end_date'].strftime('%Y-%m-%d'), 
                    row['start_date'].strftime('%Y-%m-%d'), 
                    row['start_date'].strftime('%Y-%m-%d')
                ]
                ys = [i-0.3, i-0.3, i+0.3, i+0.3, i-0.3]

                trace = {
                    'x': xs,
                    'y': ys,
                    'fill': 'toself',
                    'fillcolor': VESSEL_COLORS.get(vessel_name, '#999'),
                    'line': {'color': VESSEL_COLORS.get(vessel_name, '#999'), 'width': 2},
                    'name': vessel_name if is_first else "",
                    'showlegend': is_first,
                    'customdata': [row['voyage_id']] * len(xs),
                    'hovertemplate': (
                        f"<b>{row['start_date'].strftime('%Y-%m-%d')}_{row['end_date'].strftime('%Y-%m-%d')}</b><br>"
                        f"실린 블록 개수: {row['block_count']}<br>"
                        f"실린 블록 ID (납기일):<br>{blocks_text}<br>"
                        "<extra></extra>"
                    ),
                    'mode': 'lines',
                    'type': 'scatter'
                }
                chart_data.append(trace)

        # 년도, 월, 일 annotation 데이터 생성 (간트 차트 위에 3행으로 표시)
        annotations = []
        current_date = min_date
        current_year = None
        year_start = None
        current_month = None
        month_start = None
        
        # 각 날짜별로 일 표시 (세로로)
        date_iter = min_date
        while date_iter <= max_date:
            day_str = str(date_iter.day)
            # 일의 각 자릿수를 세로로 표시 (간격 조정)
            for idx, digit in enumerate(day_str):
                annotations.append({
                    'x': date_iter.strftime('%Y-%m-%d'),
                    'y': -0.1 - (idx * 0.15),  # 간트 차트 위로 이동, 세로 간격 조정
                    'text': digit,
                    'showarrow': False,
                    'font': {'size': 12, 'color': 'black'},  # 폰트 크기 증가
                    'bgcolor': 'white',
                    'bordercolor': 'gray',
                    'borderwidth': 0.5
                })
            date_iter += timedelta(days=1)
        
        # 년도와 월 표시
        while current_date <= max_date:
            # 년도 변경 감지
            if current_year != current_date.year:
                if current_year is not None:
                    year_mid = year_start + (current_date - timedelta(days=1) - year_start) / 2
                    annotations.append({
                        'x': year_mid.strftime('%Y-%m-%d'),
                        'y': -0.8,  # 간트 차트 위로 이동
                        'text': str(current_year),
                        'showarrow': False,
                        'font': {'size': 14, 'color': 'black'},
                        'bgcolor': 'white',
                        'bordercolor': 'black',
                        'borderwidth': 1
                    })
                current_year = current_date.year
                year_start = current_date
            
            # 월 변경 감지
            if current_month != current_date.month:
                if current_month is not None:
                    month_mid = month_start + (current_date - timedelta(days=1) - month_start) / 2
                    annotations.append({
                        'x': month_mid.strftime('%Y-%m-%d'),
                        'y': -0.4,  # 간트 차트 위로 이동
                        'text': f"{current_month}월",
                        'showarrow': False,
                        'font': {'size': 12, 'color': 'darkblue'},
                        'bgcolor': 'lightblue',
                        'bordercolor': 'blue',
                        'borderwidth': 1
                    })
                current_month = current_date.month
                month_start = current_date
            
            current_date += timedelta(days=1)
        
        # 마지막 년도와 월 추가
        if current_year is not None:
            year_mid = year_start + (max_date - year_start) / 2
            annotations.append({
                'x': year_mid.strftime('%Y-%m-%d'),
                'y': -0.8,
                'text': str(current_year),
                'showarrow': False,
                'font': {'size': 14, 'color': 'black'},
                'bgcolor': 'white',
                'bordercolor': 'black',
                'borderwidth': 1
            })
        
        if current_month is not None:
            month_mid = month_start + (max_date - month_start) / 2
            annotations.append({
                'x': month_mid.strftime('%Y-%m-%d'),
                'y': -0.4,
                'text': f"{current_month}월",
                'showarrow': False,
                'font': {'size': 12, 'color': 'darkblue'},
                'bgcolor': 'lightblue',
                'bordercolor': 'blue',
                'borderwidth': 1
            })

        chart_layout['annotations'] = annotations

        html_template = f"""
<!DOCTYPE html>
<html>
<head>
    <title>자항선 운항 스케줄 대시보드</title>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            background-color: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        .header {{
            text-align: center;
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 2px solid #eee;
        }}
        .stats {{
            display: flex;
            justify-content: space-around;
            margin-bottom: 30px;
            padding: 20px;
            background-color: #f8f9fa;
            border-radius: 8px;
        }}
        .stat-item {{
            text-align: center;
        }}
        .stat-number {{
            font-size: 2em;
            font-weight: bold;
            color: #007bff;
        }}
        .stat-label {{
            color: #666;
            margin-top: 5px;
        }}
        .chart-container {{
            margin-bottom: 30px;
            position: relative;
        }}
        .scroll-controls {{
            text-align: center;
            margin-bottom: 10px;
            padding: 10px;
            background-color: #f8f9fa;
            border-radius: 5px;
        }}
        .scroll-btn {{
            background-color: #007bff;
            color: white;
            border: none;
            padding: 8px 16px;
            margin: 0 5px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
        }}
        .scroll-btn:hover {{
            background-color: #0056b3;
        }}
        .scroll-btn:disabled {{
            background-color: #ccc;
            cursor: not-allowed;
        }}
        .info-panel {{
            background-color: #f8f9fa;
            padding: 20px;
            border-radius: 8px;
            border-left: 4px solid #007bff;
        }}
        .voyage-details {{
            background-color: white;
            padding: 15px;
            margin-top: 15px;
            border-radius: 5px;
            border: 1px solid #ddd;
        }}
        .block-list {{
            max-height: 200px;
            overflow-y: auto;
            margin-top: 10px;
        }}
        .block-item {{
            padding: 5px;
            margin: 2px 0;
            background-color: #f1f3f4;
            border-radius: 3px;
            font-size: 0.9em;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚢 자항선 운항 스케줄 대시보드</h1>
            <p>Level 3 통합 항차 배정 결과 시각화</p>
        </div>
        
        <div class="stats">
            <div class="stat-item">
                <div class="stat-number">{total_voyages}</div>
                <div class="stat-label">총 항차 수</div>
            </div>
            <div class="stat-item">
                <div class="stat-number">{total_blocks}</div>
                <div class="stat-label">배정된 블록 수</div>
            </div>
            <div class="stat-item">
                <div class="stat-number">{len(vessel_names)}</div>
                <div class="stat-label">운용 자항선 수</div>
            </div>
            <div class="stat-item">
                <div class="stat-number">{total_days}</div>
                <div class="stat-label">총 운항 기간 (일)</div>
            </div>
        </div>
        
        <div class="chart-container">
            <div class="scroll-controls">
                <button class="scroll-btn" onclick="scrollChart('start')">⏮️ 처음으로</button>
                <button class="scroll-btn" onclick="scrollChart('left')">⬅️ 이전 30일</button>
                <button class="scroll-btn" onclick="scrollChart('right')">다음 30일 ➡️</button>
                <button class="scroll-btn" onclick="scrollChart('end')">마지막으로 ⏭️</button>
                <button class="scroll-btn" onclick="resetZoom()">🔍 전체 보기</button>
            </div>
            <div id="gantt-chart"></div>
        </div>
        
        <div class="info-panel">
            <h3>📋 항차 상세 정보</h3>
            <p>간트 차트의 항차 바를 클릭하면 상세 정보가 여기에 표시됩니다.</p>
            <div id="voyage-info"></div>
        </div>
    </div>

    <script>
        // Plotly 차트를 직접 생성하여 JSON 직렬화 문제 해결
        var minDate = new Date('{min_date.strftime('%Y-%m-%d')}');
        var maxDate = new Date('{max_date.strftime('%Y-%m-%d')}');
        var currentRange = [minDate, new Date(minDate.getTime() + 60 * 24 * 60 * 60 * 1000)]; // 60일
        
        var chartData = {json.dumps(chart_data, ensure_ascii=False)};
        var chartLayout = {json.dumps(chart_layout, ensure_ascii=False)};
        
        Plotly.newPlot('gantt-chart', chartData, chartLayout, {{
            responsive: true,
            displayModeBar: true,
            modeBarButtonsToRemove: ['select2d', 'lasso2d', 'autoScale2d', 'resetScale2d'],
            scrollZoom: false
        }});
        
        // 클릭 이벤트 리스너 추가 (Plotly 방식)
        document.getElementById('gantt-chart').on('plotly_click', function(data) {{
            if (data.points && data.points.length > 0) {{
                var voyageId = data.points[0].customdata;
                if (voyageId) {{
                    showVoyageDetails(voyageId);
                }}
            }}
        }});
        
        // 스크롤 함수들
        function scrollChart(direction) {{
            var dayMs = 24 * 60 * 60 * 1000;
            var scrollDays = 30;
            
            switch(direction) {{
                case 'start':
                    currentRange = [minDate, new Date(minDate.getTime() + 60 * dayMs)];
                    break;
                case 'left':
                    var newStart = new Date(currentRange[0].getTime() - scrollDays * dayMs);
                    var newEnd = new Date(currentRange[1].getTime() - scrollDays * dayMs);
                    if (newStart >= minDate) {{
                        currentRange = [newStart, newEnd];
                    }}
                    break;
                case 'right':
                    var newStart = new Date(currentRange[0].getTime() + scrollDays * dayMs);
                    var newEnd = new Date(currentRange[1].getTime() + scrollDays * dayMs);
                    if (newEnd <= maxDate) {{
                        currentRange = [newStart, newEnd];
                    }}
                    break;
                case 'end':
                    currentRange = [new Date(maxDate.getTime() - 60 * dayMs), maxDate];
                    break;
            }}
            
            Plotly.relayout('gantt-chart', {{
                'xaxis.range': currentRange
            }});
        }}
        
        function resetZoom() {{
            currentRange = [minDate, maxDate];
            Plotly.relayout('gantt-chart', {{
                'xaxis.range': currentRange
            }});
        }}
        
        // 클릭 이벤트 처리
        document.getElementById('gantt-chart').on('plotly_click', function(data) {{
            if (data.points && data.points.length > 0) {{
                var voyageId = data.points[0].customdata;
                showVoyageDetails(voyageId);
            }}
        }});
        
        function showVoyageDetails(voyageId) {{
            var voyageData = {json.dumps(self.voyage_data, ensure_ascii=False)};
            var blocks = voyageData[voyageId] || [];
            
            var html = '<div class="voyage-details">';
            html += '<h4>🚢 ' + voyageId + '</h4>';
            html += '<p><strong>블록 수:</strong> ' + blocks.length + '개</p>';
            html += '<div class="block-list">';
            html += '<strong>실린 블록 목록:</strong><br>';
            
            blocks.forEach(function(blockId) {{
                html += '<div class="block-item">' + blockId + '</div>';
            }});
            
            html += '</div></div>';
            
            document.getElementById('voyage-info').innerHTML = html;
        }}
        
        // 키보드 단축키
        document.addEventListener('keydown', function(e) {{
            if (e.ctrlKey) {{
                switch(e.key) {{
                    case 'ArrowLeft':
                        e.preventDefault();
                        scrollChart('left');
                        break;
                    case 'ArrowRight':
                        e.preventDefault();
                        scrollChart('right');
                        break;
                    case 'Home':
                        e.preventDefault();
                        scrollChart('start');
                        break;
                    case 'End':
                        e.preventDefault();
                        scrollChart('end');
                        break;
                }}
            }}
        }});
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
