"""Disposable, fictional PDF for UI verification; contains no user's data."""
from pathlib import Path
from reportlab.pdfgen.canvas import Canvas
path=Path(__file__).resolve().parents[1]/'work/readiness-test/synthetic-cv.pdf'
path.parent.mkdir(parents=True,exist_ok=True)
c=Canvas(str(path));y=760
for line in ['Synthetic Candidate','Berlin | demo@example.invalid','PROFILE','Student with an academic Python monitoring project.','TECHNICAL SKILLS','Tools: Python, Linux, SIEM','PERSONAL PROJECTS','Built a synthetic log analysis exercise for study.','EDUCATION','Example University — Computer Science studies.']:
    c.drawString(40,y,line);y-=24
c.save();print('Synthetic CV fixture created.')
