# demo_margins.py
from plot_margins import plot_margins_from_records

# 단위: 원
data = [
    {
        "period": "2022",
        "revenue": 35500000000000,         # 35조 5,000억
        "operating_profit": 5234394000000, # 5조 2,343억 9,400만
        "net_income": 4112493000000        # 4조 1,124억 9,300만
    },
    {
        "period": "2023",
        "revenue": 44830000000000,         # 44조 8,300억
        "operating_profit": 6385021000000, # 6조 3,850억 2,100만
        "net_income": 4526334000000        # 4조 5,263억 3,400만
    },
    {
        "period": "2024",
        "revenue": 47000000000000,         # 47조
        "operating_profit": 8045261000000, # 8조 452억 6,100만
        "net_income": 5078221000000        # 5조 782억 2,100만
    }
]

plot_margins_from_records(
    data,
    title="KB금융 수익성(분모=총수익/매출)",
    out_png="margins_chart.png"
)
