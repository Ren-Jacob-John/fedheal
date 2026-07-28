"""
Populates a few realistic-looking training rounds and validation flags
directly into this service's own database — no other module needs to be
running. Useful for demoing the overview/rounds/flags endpoints (or a
future dashboard screen) before Module 2/3 are actually wired up end to
end, or before you've run a real simulation yet.

Run: python seed_demo.py   (with this module's venv active)
Then: uvicorn main:app --reload --port 8005   and hit /admin/overview
(you'll still need a real super_admin JWT from Module 1 to call it — see
this folder's README for the exact curl sequence).
"""
from database import Base, SessionLocal, engine
from models import TrainingRound, ValidationFlag

Base.metadata.create_all(bind=engine)


def main():
    db = SessionLocal()
    try:
        rounds = [
            TrainingRound(round_number=i, n_hospitals=3,
                          global_accuracy=0.70 + i * 0.015,
                          baseline_accuracy=0.68,
                          notes="seeded demo data")
            for i in range(1, 6)
        ]
        db.add_all(rounds)

        flags = [
            ValidationFlag(hospital_id="demo-hospital-a", status="rejected",
                            reason="height outside plausible range (0-272 cm)", count=2),
            ValidationFlag(hospital_id="demo-hospital-a", status="flagged",
                            reason="statistical outlier relative to batch (isolation forest)", count=5),
            ValidationFlag(hospital_id="demo-hospital-b", status="rejected",
                            reason="contains identifying field(s): patient_name", count=1),
        ]
        db.add_all(flags)

        db.commit()
        print(f"Seeded {len(rounds)} training rounds and {len(flags)} validation flag summaries "
              f"into fedheal_admin.db")
    finally:
        db.close()


if __name__ == "__main__":
    main()
