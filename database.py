from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class LottoResult(db.Model):
    """과거 당첨 번호 결과 저장"""
    __tablename__ = 'lotto_results'
    drw_no = db.Column(db.Integer, primary_key=True)  # 회차
    drw_no_date = db.Column(db.String(20))           # 추첨일
    num1 = db.Column(db.Integer, nullable=False)
    num2 = db.Column(db.Integer, nullable=False)
    num3 = db.Column(db.Integer, nullable=False)
    num4 = db.Column(db.Integer, nullable=False)
    num5 = db.Column(db.Integer, nullable=False)
    num6 = db.Column(db.Integer, nullable=False)
    bonus_num = db.Column(db.Integer, nullable=False)
    first_win_amnt = db.Column(db.BigInteger)        # 1등 당첨금
    first_przwner_co = db.Column(db.Integer)         # 1등 당첨 인원

class SavedNumber(db.Model):
    """사용자가 저장한 예측 번호 조합"""
    __tablename__ = 'saved_numbers'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    num1 = db.Column(db.Integer, nullable=False)
    num2 = db.Column(db.Integer, nullable=False)
    num3 = db.Column(db.Integer, nullable=False)
    num4 = db.Column(db.Integer, nullable=False)
    num5 = db.Column(db.Integer, nullable=False)
    num6 = db.Column(db.Integer, nullable=False)
    prediction_score = db.Column(db.Integer)         # 예측 신뢰도 점수
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_purchased = db.Column(db.Boolean, default=False) # 구매 여부
    win_rank = db.Column(db.Integer, default=0)       # 당첨 등수 (0: 미당첨)

def init_db(app):
    db.init_app(app)
    with app.app_context():
        db.create_all()
