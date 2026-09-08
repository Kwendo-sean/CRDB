"""Downloadable Excel templates for the Control Room.

Every import surface in the Control Room has a matching template here, so an
administrator never has to guess a column name. Each workbook carries:

* an INSTRUCTIONS sheet in plain language,
* a data sheet whose header row exactly matches what the importer requires,
* two worked example rows the administrator overwrites, and
* dropdown validation on the columns that only accept fixed values.

The templates are generated (not stored as binaries) so the columns can never
drift away from ``core.importers``.
"""

from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

ACCENT = "DF1F26"
HEADER_FILL = PatternFill("solid", fgColor=ACCENT)
HEADER_FONT = Font(color="FFFFFF", bold=True, size=11)
EXAMPLE_FONT = Font(italic=True, color="7A7A7A")
TITLE_FONT = Font(bold=True, size=16)
HINT_FONT = Font(color="595959", size=10)
THIN = Side(style="thin", color="D5D5D5")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def _instructions(workbook, title, lines):
    sheet = workbook.create_sheet("INSTRUCTIONS", 0)
    sheet.column_dimensions["A"].width = 110
    sheet["A1"] = title
    sheet["A1"].font = TITLE_FONT
    for index, line in enumerate(lines, start=3):
        cell = sheet.cell(row=index, column=1, value=line)
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        if not line.startswith("  "):
            cell.font = Font(bold=line.endswith(":"), size=11)
        else:
            cell.font = HINT_FONT
    sheet.sheet_view.showGridLines = False
    return sheet


def _data_sheet(workbook, name, columns, examples, widths, validations=()):
    sheet = workbook.create_sheet(name)
    for index, column in enumerate(columns, start=1):
        cell = sheet.cell(row=1, column=index, value=column)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.border = BORDER
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        sheet.column_dimensions[get_column_letter(index)].width = widths[index - 1]
    sheet.row_dimensions[1].height = 30
    for row_offset, example in enumerate(examples, start=2):
        for index, value in enumerate(example, start=1):
            cell = sheet.cell(row=row_offset, column=index, value=value)
            cell.font = EXAMPLE_FONT
            cell.border = BORDER
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    for column_index, formula in validations:
        rule = DataValidation(type="list", formula1=formula, allow_blank=True, showDropDown=False)
        rule.error = "Choose one of the listed values."
        rule.errorTitle = "Value not allowed"
        sheet.add_data_validation(rule)
        letter = get_column_letter(column_index)
        rule.add(f"{letter}2:{letter}1000")
    sheet.freeze_panes = "A2"
    return sheet


def quiz_template():
    """Questions for the official competition rounds and any interactive quiz."""
    workbook = Workbook()
    workbook.remove(workbook.active)
    _instructions(workbook, "QUIZ QUESTIONS — IMPORT TEMPLATE", [
        "How to use this file:",
        "  1. Open the QUESTIONS sheet.",
        "  2. Delete the two grey example rows.",
        "  3. Write one row per question. Keep the header row exactly as it is.",
        "  4. Save as .xlsx, then upload it in the Control Room under Experiences > Quizzes > the round > Import Questions.",
        "  5. Choose 'Validate & Preview' first. Fix anything it reports, then choose the file again and 'Import Questions'.",
        "",
        "Rules the importer enforces:",
        "  day — 1, 2, 3 or 4.",
        "  challenge_name — the round title. Every row of the same round must repeat the identical name.",
        "  question_number — 1 to 10, each used once. An official round needs exactly 10 questions.",
        "  question_text — the question as participants will read it.",
        "  answer_1 to answer_4 — all four are required. Participants see them as A, B, C, D.",
        "  correct_answer_number — 1, 2, 3 or 4, matching the answer column that is correct.",
        "  time_limit — seconds this question stays open, 5 to 3600. Use 20 or 30 for a fast round,",
        "               or 300 for five minutes per question. Each question can differ.",
        "  points — a positive whole number. The official value is 1000 per question.",
        "  host_note — the explanation the host reads out on reveal. Required.",
        "",
        "Good to know:",
        "  Nothing is imported if any row is wrong; you get a list of the exact rows to fix.",
        "  Importing replaces all questions on that round, so import before anyone plays.",
        "  Once a round has real answers recorded, its questions are locked and the import is refused.",
        "  You can put several rounds in one file, one block of 10 rows per round.",
    ])
    examples = [
        (1, "Systems Online", 1, "Which layer of a core banking system settles interbank payments?",
         "The payment switch", "The data warehouse", "The mobile channel", "The reporting layer",
         1, 20, 1000, "The payment switch routes and settles interbank instructions in real time."),
        (1, "Systems Online", 2, "What does an API gateway primarily protect?",
         "Branch queues", "Backend services", "ATM cash levels", "Printer drivers",
         2, 30, 1000, "The gateway fronts backend services with auth, throttling and routing."),
    ]
    _data_sheet(
        workbook, "QUESTIONS",
        ["day", "challenge_name", "question_number", "question_text", "answer_1", "answer_2", "answer_3", "answer_4", "correct_answer_number", "time_limit", "points", "host_note"],
        examples,
        [7, 24, 14, 52, 26, 26, 26, 26, 16, 11, 9, 52],
        validations=[(1, '"1,2,3,4"'), (9, '"1,2,3,4"'), (10, '"20,30,60,120,300"')],
    )
    return workbook


def session_template():
    """Programme sessions, which drive the timetable and QR check-in."""
    workbook = Workbook()
    workbook.remove(workbook.active)
    _instructions(workbook, "PROGRAMME SESSIONS — IMPORT TEMPLATE", [
        "How to use this file:",
        "  1. Open the SESSIONS sheet and delete the two grey example rows.",
        "  2. Write one row per programme session.",
        "  3. Save as .xlsx and upload it in the Control Room under Programme > Import Sessions.",
        "",
        "Rules the importer enforces:",
        "  source_key — your own permanent code for the session, e.g. D1-KEYNOTE. Must be unique.",
        "               Re-importing with the same source_key updates that session instead of duplicating it.",
        "  day — 1, 2, 3 or 4.",
        "  date — the calendar date, formatted YYYY-MM-DD.",
        "  start_time / end_time — 24-hour HH:MM. The end must be after the start.",
        "  title — the session name shown to participants.",
        "  facilitator — the presenter's name.",
        "  format — FACE-TO-FACE, VIRTUAL or HYBRID.",
        "  audience — who the session is for, in free text.",
        "  location — room, venue or meeting link.",
        "",
        "Good to know:",
        "  Times are read in Africa/Dar_es_Salaam.",
        "  Nothing is imported if any row is wrong; you get a list of the exact rows to fix.",
        "  Each imported session automatically appears on the participant programme and in the check-in scanner.",
    ])
    examples = [
        ("D1-KEYNOTE", 1, "2026-09-07", "09:00", "10:30", "Opening Keynote: AI and the Future of Banking",
         "Predictive Analytics Lab", "FACE-TO-FACE", "All staff", "CRDB Head Office Auditorium"),
        ("D1-WS-RISK", 1, "2026-09-07", "11:00", "12:30", "Workshop: Model Risk in Practice",
         "Risk Analytics Team", "HYBRID", "Risk and Credit teams", "Training Room 2 / Teams"),
    ]
    _data_sheet(
        workbook, "SESSIONS",
        ["source_key", "day", "date", "start_time", "end_time", "title", "facilitator", "format", "audience", "location"],
        examples,
        [16, 7, 14, 12, 12, 46, 26, 17, 28, 30],
        validations=[(2, '"1,2,3,4"'), (8, '"FACE-TO-FACE,VIRTUAL,HYBRID"')],
    )
    return workbook


def activity_template():
    """Interactive games, expo stands, AIoT demos and custom challenges."""
    workbook = Workbook()
    workbook.remove(workbook.active)
    _instructions(workbook, "INTERACTIVE GAMES & ACTIVITIES — IMPORT TEMPLATE", [
        "Use this file for anything a participant completes by being there: expo stand games,",
        "AIoT demos, scavenger hunts, stand challenges and other custom activities.",
        "",
        "How to use this file:",
        "  1. Open the ACTIVITIES sheet and delete the two grey example rows.",
        "  2. Write one row per game or stand.",
        "  3. Save as .xlsx and upload it in the Control Room under Experiences > Activities > Import Activities.",
        "",
        "Rules the importer enforces:",
        "  code — a short permanent identifier, lowercase, no spaces, e.g. aiot-demo-1.",
        "         Re-importing with the same code updates that activity instead of duplicating it.",
        "         This is also the code a stand device sends when it marks someone complete.",
        "  name — the title participants see.",
        "  description — one or two lines explaining what to do at the stand.",
        "  day — 1, 2, 3 or 4.",
        "  points — Learning XP awarded on completion. Whole number, 0 or more.",
        "  repeatable — YES or NO. NO means each participant earns the points once.",
        "",
        "Good to know:",
        "  Activity points are Learning XP. They never affect the official quiz prize ranking.",
        "  Each imported activity appears on the participant dashboard and can be marked complete",
        "  by scanning a Learning Pass at the stand.",
        "  Nothing is imported if any row is wrong; you get a list of the exact rows to fix.",
    ])
    examples = [
        ("aiot-smart-branch", "AIoT Smart Branch Demo",
         "Visit the AIoT stand and complete the smart-branch sensor walkthrough.", 2, 150, "NO"),
        ("fraud-hunt", "Fraud Hunt Challenge",
         "Find the three planted anomalies on the expo floor and confirm them at the stand.", 3, 200, "NO"),
    ]
    _data_sheet(
        workbook, "ACTIVITIES",
        ["code", "name", "description", "day", "points", "repeatable"],
        examples,
        [22, 32, 60, 7, 10, 13],
        validations=[(4, '"1,2,3,4"'), (6, '"YES,NO"')],
    )
    return workbook


def participant_template():
    """The registered roster."""
    workbook = Workbook()
    workbook.remove(workbook.active)
    _instructions(workbook, "PARTICIPANTS — IMPORT TEMPLATE", [
        "Use this file to load the registered roster in bulk, or to correct details later.",
        "",
        "How to use this file:",
        "  1. Open the PARTICIPANTS sheet and delete the two grey example rows.",
        "  2. Paste or type one row per registered person. A few thousand rows is fine.",
        "  3. Save as .xlsx and upload it in the Control Room under Participants > Import Participants.",
        "",
        "Rules the importer enforces:",
        "  staff_id — the CRDB staff number. Strongly recommended: it is what people type to sign in.",
        "  full_name — required.",
        "  email — the work email. Either staff_id or email must be present on every row.",
        "  department, job_role, phone — optional, but department drives the analytics breakdown.",
        "",
        "Good to know:",
        "  Rows are matched on staff_id first, then email, so re-importing a corrected file",
        "  updates people rather than creating duplicates.",
        "  Existing Learning Passes, QR codes, attendance and scores are never affected by a re-import.",
        "  A blank cell leaves the stored value alone; it does not erase it.",
        "  Nothing is imported if any row is wrong; you get a list of the exact rows to fix.",
        "  Participants sign in with their staff ID or email at /access/ — no password is issued.",
    ])
    examples = [
        ("CRDB0142", "Grace Mushi", "grace.mushi@crdbbank.co.tz", "Retail Banking", "Branch Manager", "+255700000001"),
        ("CRDB0287", "Juma Almasi", "juma.almasi@crdbbank.co.tz", "Technology", "Data Engineer", "+255700000002"),
    ]
    _data_sheet(
        workbook, "PARTICIPANTS",
        ["staff_id", "full_name", "email", "department", "job_role", "phone"],
        examples,
        [14, 26, 36, 24, 24, 18],
    )
    return workbook


# (day, challenge, number, question, a1, a2, a3, a4, correct, timer, points, host note)
SAMPLE_QUESTIONS = [
    (1, "AI Infrastructure Trivia Sprint", 1,
     "In a core banking system, which component routes and settles interbank payment instructions?",
     "The payment switch", "The data warehouse", "The mobile channel", "The reporting layer",
     1, 20, 1000,
     "The payment switch routes and settles interbank instructions in real time. The warehouse and reporting layer only read data after the fact."),
    (1, "AI Infrastructure Trivia Sprint", 2,
     "An API gateway sits in front of backend banking services primarily to do what?",
     "Store customer balances", "Authenticate, throttle and route requests", "Print branch statements", "Replace the core ledger",
     2, 20, 1000,
     "The gateway is the front door: it authenticates callers, throttles abuse and routes each request to the right service. It never holds the ledger itself."),
    (1, "AI Infrastructure Trivia Sprint", 3,
     "In fraud analytics, what is an anomaly?",
     "Any transaction above 1,000,000 TZS", "A transaction that deviates from established behaviour patterns",
     "A failed card payment", "A transaction made outside branch hours",
     2, 20, 1000,
     "An anomaly is defined against the customer's own behaviour, not a fixed dictionary rule. A large or late transaction is only suspicious if it is unusual for that customer."),
    (1, "AI Infrastructure Trivia Sprint", 4,
     "A fraud model blocks a genuine customer transaction. What is this outcome called?",
     "A false negative", "A true positive", "A false positive", "A model drift event",
     3, 20, 1000,
     "A false positive is a legitimate action wrongly flagged. It is the error that damages customer trust, which is why fraud teams tune for it carefully."),
    (1, "AI Infrastructure Trivia Sprint", 5,
     "What does eKYC allow a bank to do?",
     "Verify a customer's identity remotely using digital documents and biometrics",
     "Encrypt the customer's card PIN", "Extend a customer's overdraft automatically", "Keep records of closed accounts",
     1, 30, 1000,
     "eKYC is electronic Know Your Customer: identity verification done remotely and digitally, so onboarding does not require a branch visit."),
    (1, "AI Infrastructure Trivia Sprint", 6,
     "Which machine learning approach trains a model on labelled historical outcomes?",
     "Unsupervised learning", "Supervised learning", "Reinforcement learning", "Clustering",
     2, 20, 1000,
     "Supervised learning needs labelled examples — past loans marked repaid or defaulted, past transactions marked fraud or genuine."),
    (1, "AI Infrastructure Trivia Sprint", 7,
     "In credit scoring, which of these is a behavioural feature rather than a demographic one?",
     "The applicant's age", "The applicant's home region", "Repayment history on previous loans", "The applicant's gender",
     3, 20, 1000,
     "Behavioural features describe what someone has actually done. Repayment history is behaviour; age, region and gender are demographics, and several are protected attributes."),
    (1, "AI Infrastructure Trivia Sprint", 8,
     "Which of these counts as personally identifiable information (PII)?",
     "The branch opening time", "A national identification number", "The bank's published exchange rate", "The number of ATMs in a region",
     2, 20, 1000,
     "PII is any data that identifies a specific person. A national ID number does; published rates and branch details do not."),
    (1, "AI Infrastructure Trivia Sprint", 9,
     "Which technology lets a banking chatbot interpret a customer's typed question?",
     "Optical character recognition", "Natural language processing", "Robotic process automation", "Blockchain settlement",
     2, 30, 1000,
     "Natural language processing turns free text into structured intent. OCR reads images, RPA automates clicks, and neither understands language."),
    (1, "AI Infrastructure Trivia Sprint", 10,
     "A deployed credit model slowly becomes less accurate as customer behaviour changes. What is this called?",
     "Model drift", "Overfitting", "A false positive", "Feature engineering",
     1, 30, 1000,
     "Model drift is the real world moving away from the data the model was trained on. It is why deployed models need monitoring and periodic retraining."),
]


def sample_quiz():
    """A complete, ready-to-import ten-question round for Day 1.

    Same columns as the blank template, already filled in, so an administrator can
    see exactly what a valid file looks like and can import it as a dry run.
    """
    workbook = Workbook()
    workbook.remove(workbook.active)
    _instructions(workbook, "SAMPLE QUIZ — AI INFRASTRUCTURE TRIVIA SPRINT (DAY 1)", [
        "This is a worked example, not a blank template. It already contains ten valid",
        "questions and can be imported exactly as it is.",
        "",
        "Use it to:",
        "  Practise the import before the event, on a round that does not matter.",
        "  See what correct question text, distractors and host notes look like.",
        "  Start your own round — overwrite the question text and keep the structure.",
        "",
        "To import it:",
        "  1. Control Room > Experiences > Quizzes > pick or create a round.",
        "  2. Import Questions > Validate & Preview.",
        "  3. Select the file again and choose Import Questions.",
        "  4. Publish / Schedule Quiz, then Control to run it live.",
        "",
        "Note on the columns:",
        "  challenge_name is repeated identically on all ten rows. That is what groups",
        "  them into one round.",
        "  correct_answer_number points at the answer column that is correct, so a 1",
        "  means answer_1 is right.",
        "  Blank rows are ignored, but a wrong value anywhere rejects the whole file.",
        "",
        "For a blank version of this file, download the QUIZ QUESTIONS template.",
    ])
    _data_sheet(
        workbook, "QUESTIONS",
        ["day", "challenge_name", "question_number", "question_text", "answer_1", "answer_2", "answer_3", "answer_4", "correct_answer_number", "time_limit", "points", "host_note"],
        SAMPLE_QUESTIONS,
        [7, 26, 14, 56, 28, 28, 28, 28, 16, 11, 9, 60],
        validations=[(1, '"1,2,3,4"'), (9, '"1,2,3,4"'), (10, '"20,30"')],
    )
    # Worked rows are real content, not placeholders to delete, so drop the grey italics.
    sheet = workbook["QUESTIONS"]
    for row in sheet.iter_rows(min_row=2):
        for cell in row:
            cell.font = Font()
    return workbook


EXPO_GAMES = [
    ("vr-games", "VR Games",
     "Step into the VR station and complete a banking scenario in virtual reality.", 1, 200, "NO"),
    ("robot-assembly", "Robot Assembly",
     "Build and program the robot at the assembly bench with the engineering team.", 1, 250, "NO"),
    ("arduino-assembly", "Arduino Assembly",
     "Wire and flash an Arduino board to bring a sensor to life.", 1, 250, "NO"),
]


def expo_games():
    """The three expo games as a ready-to-import sheet.

    Lets a fresh server load the real stand line-up in one command instead of
    retyping it in the Control Room. Edit the points here or in the Control Room.
    """
    workbook = Workbook()
    workbook.remove(workbook.active)
    _instructions(workbook, "EXPO GAMES — READY TO IMPORT", [
        "The three interactive games on the expo floor, ready to import as they are.",
        "",
        "To load them on a fresh server:",
        "  docker compose exec web python manage.py import_activities import_templates/expo-games.xlsx",
        "",
        "Or upload this file at Control Room > Experiences > Interactive Games > Import from Excel.",
        "",
        "After importing, each game appears:",
        "  on every participant's dashboard under INTERACTIVE GAMES, and",
        "  in the QR scanner's game list, so a stand operator can award its points.",
        "",
        "Change the points by editing the points column and importing again, or in the",
        "Control Room. Re-importing matches on the code column, so nothing is duplicated",
        "and no already-awarded points are disturbed.",
    ])
    _data_sheet(
        workbook, "ACTIVITIES",
        ["code", "name", "description", "day", "points", "repeatable"],
        EXPO_GAMES,
        [22, 26, 62, 7, 10, 13],
        validations=[(4, '"1,2,3,4"'), (6, '"YES,NO"')],
    )
    sheet = workbook["ACTIVITIES"]
    for row in sheet.iter_rows(min_row=2):
        for cell in row:
            cell.font = Font()
    return workbook


TEMPLATES = {
    "quiz-questions": ("quiz-questions-template.xlsx", quiz_template),
    "programme-sessions": ("programme-sessions-template.xlsx", session_template),
    "activities": ("interactive-activities-template.xlsx", activity_template),
    "participants": ("participants-template.xlsx", participant_template),
    "sample-quiz": ("sample-quiz-day1-ai-infrastructure.xlsx", sample_quiz),
    "expo-games": ("expo-games.xlsx", expo_games),
}


def template_bytes(key):
    """Return (filename, xlsx bytes) for a template key, or raise KeyError."""
    filename, builder = TEMPLATES[key]
    stream = BytesIO()
    builder().save(stream)
    return filename, stream.getvalue()
