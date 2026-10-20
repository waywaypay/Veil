"""14 HTML templates imitating employee-copy W-2 prints from various payroll
providers / employer portals.  Each function takes the form dict and returns a
complete HTML document (inline CSS only, no JS, no external resources)."""

from html import escape as _esc


# ----------------------------------------------------------------- helpers
def e(s):
    return _esc(s or "", quote=True)


def g(f, k, default=""):
    v = f.get(k)
    return default if v is None else str(v)


def year(f):
    return g(f, "year") or "2025"


def addr(f):
    lines = [l for l in g(f, "address").split("\n") if l.strip()]
    while len(lines) < 2:
        lines.append("")
    return lines


def emp_lines(f):
    lines = [l for l in g(f, "employer").split("\n") if l.strip()]
    if not lines:
        lines = [g(f, "employer_name"), g(f, "employer_street")]
    return lines


def mask(ssn):
    return "XXX-XX-" + ssn[-4:] if len(ssn) >= 4 else ssn


def box12(f):
    out = []
    for s in "abcd":
        c, a = g(f, "c12" + s), g(f, "a12" + s)
        if c or a:
            out.append((s, c, a))
    return out


def b12_slot(f, i):
    items = box12(f)
    letter = "abcd"[i]
    for s, c, a in items:
        if s == letter:
            return c, a
    return "", ""


def doc(title, css, body, page="size: letter; margin: 0.5in;"):
    return ("<!DOCTYPE html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
            f"<title>{e(title)}</title><style>@page {{ {page} }}\n"
            "* { box-sizing: border-box; } html, body { margin: 0; padding: 0; }\n"
            f"{css}</style></head><body>{body}</body></html>")


def br(lines):
    return "<br>".join(e(l) for l in lines)


# ======================================================== 1. IRS grid classic
CSS1 = """
body { font-family: Arial, Helvetica, sans-serif; font-size: 8pt; color: #000; }
.hdr { display: flex; justify-content: space-between; align-items: flex-end; margin-bottom: 4px; }
.hdr .l { font-size: 9pt; font-weight: bold; }
.hdr .r { font-size: 7pt; text-align: right; }
table.w2 { width: 100%; border-collapse: collapse; table-layout: fixed; }
table.w2 td { border: 1px solid #000; vertical-align: top; padding: 2px 4px; height: 34px; }
.cap { font-size: 6.5pt; display: block; margin-bottom: 2px; }
.val { font-size: 9pt; font-family: "Courier New", monospace; }
.tall { height: 70px !important; }
.foot { display: flex; justify-content: space-between; margin-top: 4px; font-size: 7.5pt; }
.big { font-size: 15pt; font-weight: bold; }
.instr { margin-top: 18px; font-size: 7pt; column-count: 2; column-gap: 18px; border-top: 1px dashed #000; padding-top: 8px; }
"""


def t01_irs_grid_classic(f):
    a = addr(f)
    c12 = [b12_slot(f, i) for i in range(4)]
    cells12 = "".join(
        f'<td><span class="cap">12{"abcd"[i]} &nbsp; Code</span>'
        f'<span class="val">{e(c)} &nbsp; {e(v)}</span></td>' for i, (c, v) in enumerate(c12))
    body = f"""
<div class="hdr"><div class="l">Copy B&mdash;To Be Filed With Employee's FEDERAL Tax Return</div>
<div class="r">OMB No. 1545-0008<br>This information is being furnished to the Internal Revenue Service.</div></div>
<table class="w2">
<tr><td colspan="2"><span class="cap">a Employee's social security number</span><span class="val">{e(g(f,'ssn'))}</span></td>
<td colspan="2" style="border:none"></td></tr>
<tr><td colspan="2"><span class="cap">b Employer identification number (EIN)</span><span class="val">{e(g(f,'ein'))}</span></td>
<td><span class="cap">1 Wages, tips, other compensation</span><span class="val">{e(g(f,'w1'))}</span></td>
<td><span class="cap">2 Federal income tax withheld</span><span class="val">{e(g(f,'w2'))}</span></td></tr>
<tr><td colspan="2" rowspan="3" class="tall"><span class="cap">c Employer's name, address, and ZIP code</span><span class="val">{br(emp_lines(f))}</span></td>
<td><span class="cap">3 Social security wages</span><span class="val">{e(g(f,'w3'))}</span></td>
<td><span class="cap">4 Social security tax withheld</span><span class="val">{e(g(f,'w4'))}</span></td></tr>
<tr><td><span class="cap">5 Medicare wages and tips</span><span class="val">{e(g(f,'w5'))}</span></td>
<td><span class="cap">6 Medicare tax withheld</span><span class="val">{e(g(f,'w6'))}</span></td></tr>
<tr><td><span class="cap">7 Social security tips</span></td><td><span class="cap">8 Allocated tips</span></td></tr>
<tr><td colspan="2"><span class="cap">d Control number</span><span class="val">{e(g(f,'control'))}</span></td>
<td><span class="cap">9</span></td><td><span class="cap">10 Dependent care benefits</span></td></tr>
<tr><td colspan="2" rowspan="3" class="tall"><span class="cap">e Employee's first name and initial &nbsp;&nbsp;&nbsp; Last name &nbsp;&nbsp;&nbsp; Suff.</span>
<span class="val">{e(g(f,'first'))} {e(g(f,'last'))}<br>{e(a[0])}<br>{e(a[1])}</span>
<span class="cap" style="margin-top:4px">f Employee's address and ZIP code</span></td>
<td><span class="cap">11 Nonqualified plans</span></td><td><span class="cap">12a &nbsp; Code</span><span class="val">{e(c12[0][0])} &nbsp; {e(c12[0][1])}</span></td></tr>
<tr><td><span class="cap">13 Statutory employee &nbsp; Retirement plan &nbsp; Third-party sick pay</span><span class="val">&#9744; &nbsp; &#9744; &nbsp; &#9744;</span></td>
<td><span class="cap">12b &nbsp; Code</span><span class="val">{e(c12[1][0])} &nbsp; {e(c12[1][1])}</span></td></tr>
<tr><td><span class="cap">14 Other</span></td>
<td><span class="cap">12c &nbsp; Code</span><span class="val">{e(c12[2][0])} &nbsp; {e(c12[2][1])}</span></td></tr>
</table>
<table class="w2" style="margin-top:-1px">
<tr><td style="width:7%"><span class="cap">15 State</span><span class="val">{e(g(f,'state1'))}</span></td>
<td style="width:21%"><span class="cap">Employer's state ID number</span><span class="val">{e(g(f,'stid1'))}</span></td>
<td><span class="cap">16 State wages, tips, etc.</span><span class="val">{e(g(f,'sw1'))}</span></td>
<td><span class="cap">17 State income tax</span><span class="val">{e(g(f,'st1'))}</span></td>
<td><span class="cap">18 Local wages, tips, etc.</span></td>
<td><span class="cap">19 Local income tax</span></td>
<td><span class="cap">20 Locality name</span></td></tr>
</table>
<div class="foot"><div>Form <span class="big">W-2</span> Wage and Tax Statement</div><div class="big">{e(year(f))}</div>
<div>Department of the Treasury&mdash;Internal Revenue Service</div></div>
<div class="instr"><b>Notice to Employee</b><br>Do you have to file? Refer to the Form 1040 instructions to determine if you are
required to file a tax return. Even if you don't have to file a tax return, you may be eligible for a refund if box 2 shows an amount
or if you are eligible for any credit.<br><br><b>Earned income credit (EIC).</b> You may be able to take the EIC for {e(year(f))} if your adjusted
gross income (AGI) is less than a certain amount.<br><br><b>Corrections.</b> If your name, SSN, or address is incorrect, correct Copies B, C,
and 2 and ask your employer to correct your employment record.</div>
"""
    return doc("W-2 Copy B", CSS1, body)


# ============================================ 2. captions inside, two copies
CSS2 = """
body { font-family: "Times New Roman", Times, serif; font-size: 8pt; }
.copy { height: 4.8in; position: relative; }
.cut { border-top: 1px dashed #555; margin: 10px 0 14px; text-align: center; font-size: 6.5pt; color: #555; font-family: Arial, sans-serif; }
.g { display: grid; grid-template-columns: 1.2fr 1.2fr 1fr 1fr; border-left: 1.5px solid #000; border-top: 1.5px solid #000; }
.g > div { border-right: 1.5px solid #000; border-bottom: 1.5px solid #000; position: relative; min-height: 0.36in; padding: 10px 5px 3px; }
.g > div i { position: absolute; top: 1px; left: 3px; font-size: 6pt; font-style: normal; color: #222; }
.g > div b { font-weight: normal; font-size: 9.5pt; display: block; text-align: right; }
.g > div b.l { text-align: left; }
.s2 { grid-column: span 2; } .r3 { grid-row: span 3; } .s4 { grid-column: span 4; }
.st { display: grid; grid-template-columns: 0.4fr 1.3fr 1fr 1fr 1fr 1fr 0.8fr; border-left: 1.5px solid #000; }
.st > div { border-right: 1.5px solid #000; border-bottom: 1.5px solid #000; position: relative; min-height: 0.36in; padding: 10px 5px 3px; }
.st > div i { position: absolute; top: 1px; left: 3px; font-size: 6pt; font-style: normal; }
.st > div b { font-weight: normal; font-size: 9.5pt; display: block; text-align: right; }
.bot { display: flex; justify-content: space-between; margin-top: 3px; }
.bot .f { font-size: 14pt; font-weight: bold; font-family: Arial, sans-serif; }
.tag { font-family: Arial, sans-serif; font-size: 7pt; text-align: right; margin-bottom: 2px; }
"""


def _copy2(f, label):
    a = addr(f)
    s = []
    for i in range(4):
        c, v = b12_slot(f, i)
        s.append(f'<div><i>12{"abcd"[i]} See instructions for box 12</i><b>{e(c)} &nbsp;&nbsp; {e(v)}</b></div>')
    return f"""<div class="copy"><div class="tag">{label}</div>
<div class="g">
<div><i>a Employee's social security number</i><b class="l">{e(g(f,'ssn'))}</b></div>
<div><i>OMB No. 1545-0008</i><b class="l">&nbsp;</b></div>
<div><i>1 Wages, tips, other comp.</i><b>{e(g(f,'w1'))}</b></div>
<div><i>2 Federal income tax withheld</i><b>{e(g(f,'w2'))}</b></div>
<div class="s2"><i>b Employer identification number (EIN)</i><b class="l">{e(g(f,'ein'))}</b></div>
<div><i>3 Social security wages</i><b>{e(g(f,'w3'))}</b></div>
<div><i>4 Social security tax withheld</i><b>{e(g(f,'w4'))}</b></div>
<div class="s2 r3"><i>c Employer's name, address, and ZIP code</i><b class="l">{br(emp_lines(f))}</b></div>
<div><i>5 Medicare wages and tips</i><b>{e(g(f,'w5'))}</b></div>
<div><i>6 Medicare tax withheld</i><b>{e(g(f,'w6'))}</b></div>
<div><i>7 Social security tips</i><b>&nbsp;</b></div>
<div><i>8 Allocated tips</i><b>&nbsp;</b></div>
<div><i>9</i><b>&nbsp;</b></div>
<div><i>10 Dependent care benefits</i><b>&nbsp;</b></div>
<div class="s2"><i>d Control number</i><b class="l">{e(g(f,'control'))}</b></div>
<div><i>11 Nonqualified plans</i><b>&nbsp;</b></div>{s[0]}
<div class="s2 r3"><i>e/f Employee's name, address, and ZIP code</i><b class="l">{e(g(f,'first'))} {e(g(f,'last'))}<br>{e(a[0])}<br>{e(a[1])}</b></div>
<div><i>13 Stat. emp. / Ret. plan / 3rd party sick</i><b class="l">&nbsp;</b></div>{s[1]}
<div><i>14 Other</i><b>&nbsp;</b></div>{s[2]}
<div><i>&nbsp;</i><b>&nbsp;</b></div>{s[3]}
</div>
<div class="st">
<div><i>15 State</i><b>{e(g(f,'state1'))}</b></div>
<div><i>Employer's state ID no.</i><b>{e(g(f,'stid1'))}</b></div>
<div><i>16 State wages</i><b>{e(g(f,'sw1'))}</b></div>
<div><i>17 State income tax</i><b>{e(g(f,'st1'))}</b></div>
<div><i>18 Local wages</i><b>&nbsp;</b></div>
<div><i>19 Local income tax</i><b>&nbsp;</b></div>
<div><i>20 Locality</i><b>&nbsp;</b></div>
</div>
<div class="bot"><span>Form <span class="f">W-2</span> Wage and Tax Statement &nbsp; <span class="f">{e(year(f))}</span></span>
<span>Dept. of the Treasury &ndash; IRS</span></div></div>"""


def t02_irs_two_copies(f):
    body = (_copy2(f, "Copy B &ndash; To Be Filed With Employee's FEDERAL Tax Return")
            + '<div class="cut">&#9986; - - - - - - - - - - fold and tear along perforation - - - - - - - - - -</div>'
            + _copy2(f, "Copy 2 &ndash; To Be Filed With Employee's State, City, or Local Income Tax Return"))
    return doc("Form W-2 Employee Copies", CSS2, body, "size: letter; margin: 0.4in 0.45in;")


# ============================================ 3. gray band values, ALL CAPS
CSS3 = """
body { font-family: Helvetica, Arial, sans-serif; font-size: 7.5pt; }
.top { background: #1d3a5f; color: #fff; padding: 6px 10px; display: flex; justify-content: space-between; font-size: 9pt; }
.top b { font-size: 11pt; letter-spacing: 1px; }
table { width: 100%; border-collapse: collapse; margin-top: 6px; }
td { border: 0.75pt solid #777; padding: 0; vertical-align: top; width: 25%; }
td .c { padding: 2px 4px; font-size: 6.5pt; color: #333; text-transform: uppercase; }
td .v { background: #e3e3e3; padding: 3px 5px; font-weight: bold; font-size: 9pt; min-height: 15px; font-family: "Lucida Console", Monaco, monospace; }
td .v.r { text-align: right; }
.sub { margin-top: 8px; font-size: 7pt; color: #444; border-top: 2px solid #1d3a5f; padding-top: 4px; display: flex; justify-content: space-between; }
"""


def t03_gray_band_caps(f):
    a = addr(f)
    up = lambda s: e(s.upper())
    c = lambda cap, val, r=True, span=1: (f'<td colspan="{span}"><div class="c">{cap}</div>'
                                          f'<div class="v{" r" if r else ""}">{val or "&nbsp;"}</div></td>')
    s12 = [b12_slot(f, i) for i in range(4)]
    body = f"""<div class="top"><span><b>PAYCENTRAL</b> &nbsp; Year-End Tax Services</span>
<span>{e(year(f))} W-2 &nbsp;|&nbsp; COPY C &mdash; FOR EMPLOYEE'S RECORDS</span></div>
<table>
<tr>{c("a Employee's SSN", e(g(f,'ssn')), False)}{c("b Employer ID number (EIN)", e(g(f,'ein')), False)}
{c("1 Wages, tips, other comp.", e(g(f,'w1')))}{c("2 Federal income tax withheld", e(g(f,'w2')))}</tr>
<tr><td colspan="2" rowspan="2"><div class="c">c Employer's name, address and ZIP code</div><div class="v">{"<br>".join(up(l) for l in emp_lines(f))}</div></td>
{c("3 Social security wages", e(g(f,'w3')))}{c("4 Social security tax withheld", e(g(f,'w4')))}</tr>
<tr>{c("5 Medicare wages and tips", e(g(f,'w5')))}{c("6 Medicare tax withheld", e(g(f,'w6')))}</tr>
<tr>{c("d Control number", e(g(f,'control')), False, 2)}{c("7 Social security tips", "")}{c("8 Allocated tips", "")}</tr>
<tr><td colspan="2" rowspan="3"><div class="c">e Employee's name &nbsp; f Address and ZIP code</div>
<div class="v">{up(g(f,'last'))}, {up(g(f,'first'))}<br>{up(a[0])}<br>{up(a[1])}</div></td>
{c("10 Dependent care benefits", "")}{c("11 Nonqualified plans", "")}</tr>
<tr>{c("12a Code / Amount", (e(s12[0][0]) + " &nbsp; " + e(s12[0][1])) if s12[0][0] else "")}{c("12b Code / Amount", (e(s12[1][0]) + " &nbsp; " + e(s12[1][1])) if s12[1][0] else "")}</tr>
<tr>{c("13 Stat emp / Ret plan / 3P sick", "", False)}{c("14 Other", "", False)}</tr>
</table>
<table>
<tr>{c("15 State", e(g(f,'state1')), False)}{c("Employer's state ID", e(g(f,'stid1')), False)}{c("16 State wages", e(g(f,'sw1')))}{c("17 State income tax", e(g(f,'st1')))}</tr>
<tr>{c("18 Local wages", "")}{c("19 Local income tax", "")}{c("20 Locality name", "", False)}{c("&nbsp;", "", False)}</tr>
</table>
<div class="sub"><span>Form W-2 Wage and Tax Statement {e(year(f))} &mdash; Department of the Treasury, Internal Revenue Service</span><span>Page 1 of 1</span></div>
"""
    return doc("W-2 Copy C", CSS3, body)


# =========================================== 4. statement: label left / right
CSS4 = """
body { font-family: "Segoe UI", Roboto, Arial, sans-serif; font-size: 10pt; color: #222; }
.wrap { max-width: 6.2in; margin: 0 auto; }
h1 { font-size: 16pt; font-weight: 600; margin: 0; }
.muted { color: #666; font-size: 9pt; }
.banner { background: #f2f7f4; border-left: 4px solid #2e8b57; padding: 8px 12px; margin: 14px 0; }
.row { display: flex; justify-content: space-between; padding: 5px 0; border-bottom: 1px solid #e4e4e4; }
.row span:last-child { font-weight: 600; text-align: right; }
h2 { font-size: 10.5pt; text-transform: uppercase; letter-spacing: .5px; color: #2e8b57; margin: 16px 0 4px; }
.foot { margin-top: 20px; font-size: 8pt; color: #777; }
"""


def t04_statement_lr(f):
    a = addr(f)
    R = lambda l, v: f'<div class="row"><span>{l}</span><span>{v}</span></div>'
    b12 = "".join(R(f"Box 12{s} &mdash; Code {e(c)}", e(v)) for s, c, v in box12(f))
    body = f"""<div class="wrap">
<div class="muted">Greenleaf Payroll &middot; Documents &middot; Tax forms</div>
<h1>Form W-2, Wage and Tax Statement</h1>
<div class="muted">Tax year {e(year(f))} &middot; Employee copy</div>
<div class="banner"><b>{e(g(f,'first'))} {e(g(f,'last'))}</b><br>{e(a[0])}, {e(a[1])}</div>
<h2>Identification</h2>
{R("Social security number", e(g(f,'ssn')))}
{R("Employer", e(g(f,'employer_name') or emp_lines(f)[0]))}
{R("Employer address", e(", ".join(emp_lines(f)[1:])))}
{R("Employer identification number", e(g(f,'ein')))}
{R("Control number", e(g(f,'control')) or "&mdash;")}
<h2>Federal</h2>
{R("Box 1 &mdash; Wages, tips, other compensation", e(g(f,'w1')))}
{R("Box 2 &mdash; Federal income tax withheld", e(g(f,'w2')))}
{R("Box 3 &mdash; Social security wages", e(g(f,'w3')))}
{R("Box 4 &mdash; Social security tax withheld", e(g(f,'w4')))}
{R("Box 5 &mdash; Medicare wages and tips", e(g(f,'w5')))}
{R("Box 6 &mdash; Medicare tax withheld", e(g(f,'w6')))}
{b12}
<h2>State</h2>
{R("Box 15 &mdash; State", e(g(f,'state1')))}
{R("Box 15 &mdash; Employer state ID number", e(g(f,'stid1')))}
{R("Box 16 &mdash; State wages, tips, etc.", e(g(f,'sw1')))}
{R("Box 17 &mdash; State income tax", e(g(f,'st1')))}
<div class="foot">This is a substitute statement prepared from your employer's payroll records. Keep it with your tax records.
Report these amounts on your {e(year(f))} federal and state income tax returns.</div>
</div>"""
    return doc("Form W-2 Statement", CSS4, body, "size: letter; margin: 0.75in;")


# ===================================== 5. label above value cards, SSN masked
CSS5 = """
body { font-family: Verdana, Geneva, sans-serif; font-size: 8.5pt; color: #1b1b1b; }
.head { display: flex; justify-content: space-between; border-bottom: 3px solid #6a3fa0; padding-bottom: 6px; }
.logo { font-weight: bold; font-size: 13pt; color: #6a3fa0; }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 12px; }
.card { border: 1px solid #c9c0d8; border-radius: 6px; padding: 8px 10px; }
.card h3 { margin: 0 0 6px; font-size: 8pt; color: #6a3fa0; text-transform: uppercase; }
.f { margin-bottom: 6px; }
.f label { display: block; font-size: 7pt; color: #666; }
.f div { font-size: 10pt; font-weight: bold; }
.pair { display: grid; grid-template-columns: 1fr 1fr; gap: 4px 12px; }
.note { margin-top: 12px; font-size: 7pt; color: #555; }
"""


def t05_cards_masked(f):
    a = addr(f)
    F = lambda l, v: f'<div class="f"><label>{l}</label><div>{v or "&nbsp;"}</div></div>'
    b12 = "".join(F(f"12{s} Code {e(c)}", e(v)) for s, c, v in box12(f)) or F("12", "")
    body = f"""<div class="head"><div class="logo">brightpath<span style="font-weight:normal">HR</span></div>
<div style="text-align:right">W-2 Wage and Tax Statement<br><b>{e(year(f))}</b> &middot; Employee Self Service</div></div>
<div class="grid">
<div class="card"><h3>Employee</h3>
<div class="pair">{F("First name", e(g(f,'first')))}{F("Last name", e(g(f,'last')))}</div>
{F("Address", e(a[0]) + "<br>" + e(a[1]))}
{F("Social security number", e(mask(g(f,'ssn'))))}</div>
<div class="card"><h3>Employer</h3>
{F("Name and address", br(emp_lines(f)))}
<div class="pair">{F("EIN", e(g(f,'ein')))}{F("Control number", e(g(f,'control')))}</div></div>
<div class="card"><h3>Federal wages &amp; taxes</h3><div class="pair">
{F("1 Wages, tips, other comp.", e(g(f,'w1')))}{F("2 Federal income tax withheld", e(g(f,'w2')))}
{F("3 Social security wages", e(g(f,'w3')))}{F("4 Social security tax withheld", e(g(f,'w4')))}
{F("5 Medicare wages and tips", e(g(f,'w5')))}{F("6 Medicare tax withheld", e(g(f,'w6')))}</div></div>
<div class="card"><h3>Box 12 &amp; state</h3><div class="pair">{b12}
{F("15 State", e(g(f,'state1')))}{F("Employer state ID", e(g(f,'stid1')))}
{F("16 State wages", e(g(f,'sw1')))}{F("17 State income tax", e(g(f,'st1')))}</div></div>
</div>
<div class="note">For security, your Social Security number is partially masked on this printout. The complete number is reported to the
IRS and the Social Security Administration. Printed from Employee Self Service.</div>"""
    return doc("W-2 Employee Self Service", CSS5, body)


# =========================================== 6. Box / Description / Amount table
CSS6 = """
body { font-family: Georgia, "Times New Roman", serif; font-size: 9.5pt; }
.title { text-align: center; border-bottom: 2px solid #000; padding-bottom: 6px; }
.title div:first-child { font-size: 14pt; font-weight: bold; }
.parties { display: flex; gap: 24px; margin: 12px 0; }
.parties > div { flex: 1; }
.parties h4 { margin: 0 0 3px; font-size: 8pt; text-transform: uppercase; border-bottom: 1px solid #999; }
table { width: 100%; border-collapse: collapse; }
th { background: #333; color: #fff; text-align: left; padding: 4px 6px; font-size: 8.5pt; }
td { padding: 4px 6px; border-bottom: 1px solid #ccc; }
td.n { text-align: right; font-family: "Courier New", monospace; }
tr:nth-child(even) td { background: #f5f5f5; }
.foot { margin-top: 10px; font-size: 7.5pt; color: #444; }
"""


def t06_box_table(f):
    a = addr(f)
    rows = [("a", "Employee's social security number", g(f, "ssn")),
            ("b", "Employer identification number (EIN)", g(f, "ein")),
            ("d", "Control number", g(f, "control")),
            ("1", "Wages, tips, other compensation", g(f, "w1")),
            ("2", "Federal income tax withheld", g(f, "w2")),
            ("3", "Social security wages", g(f, "w3")),
            ("4", "Social security tax withheld", g(f, "w4")),
            ("5", "Medicare wages and tips", g(f, "w5")),
            ("6", "Medicare tax withheld", g(f, "w6"))]
    for s, c, v in box12(f):
        rows.append((f"12{s}", f"Code {c}", v))
    rows += [("15", "State", g(f, "state1")),
             ("15", "Employer's state ID number", g(f, "stid1")),
             ("16", "State wages, tips, etc.", g(f, "sw1")),
             ("17", "State income tax", g(f, "st1"))]
    tr = "".join(f'<tr><td>{e(b)}</td><td>{e(d)}</td><td class="n">{e(v)}</td></tr>' for b, d, v in rows)
    body = f"""<div class="title"><div>Form W-2 Wage and Tax Statement &mdash; {e(year(f))}</div>
<div>Copy B &mdash; To Be Filed With Employee's Federal Tax Return</div></div>
<div class="parties"><div><h4>Employee</h4>{e(g(f,'last'))}, {e(g(f,'first'))}<br>{e(a[0])}<br>{e(a[1])}</div>
<div><h4>Employer</h4>{br(emp_lines(f))}</div></div>
<table><tr><th style="width:12%">Box</th><th>Description</th><th style="width:28%;text-align:right">Amount</th></tr>{tr}</table>
<div class="foot">Generated by the HR and payroll system. Boxes not listed are blank. OMB No. 1545-0008.</div>"""
    return doc("W-2 Box Detail", CSS6, body, "size: letter; margin: 0.7in;")


# ================================================ 7. monospace line-printer
CSS7 = """
body { font-family: "Courier New", Courier, monospace; font-size: 9pt; }
pre { margin: 0; font-family: inherit; font-size: inherit; line-height: 1.25; }
.paper { border: 1px solid #999; padding: 12px; background: repeating-linear-gradient(#fff 0 2.5em, #eef5ee 2.5em 5em); }
"""


def t07_line_printer(f):
    a = addr(f)
    U = lambda s: (s or "").upper()
    W = lambda s, n: (s or "")[:n].ljust(n)
    R = lambda s, n: (s or "").rjust(n)
    el = emp_lines(f)
    c12 = [b12_slot(f, i) for i in range(2)]
    lines = [
        "-" * 78,
        f" FORM W-2  WAGE AND TAX STATEMENT {year(f)}           COPY 2 - STATE/CITY/LOCAL RETURN",
        "-" * 78,
        f" A  EMPLOYEE SSN       {W(g(f,'ssn'),18)}  1 WAGES,TIPS,OTHER   {R(g(f,'w1'),14)}",
        f" B  EMPLOYER EIN       {W(g(f,'ein'),18)}  2 FED INCOME TAX     {R(g(f,'w2'),14)}",
        f" D  CONTROL NO         {W(g(f,'control'),18)}  3 SOC SEC WAGES      {R(g(f,'w3'),14)}",
        f"                                          4 SOC SEC TAX        {R(g(f,'w4'),14)}",
        f" C  EMPLOYER                              5 MEDICARE WAGES     {R(g(f,'w5'),14)}",
        f"    {W(U(el[0]),36)}  6 MEDICARE TAX       {R(g(f,'w6'),14)}",
        f"    {W(U(el[1]) if len(el)>1 else '',36)}  12A {W(c12[0][0],3)}              {R(c12[0][1],14)}",
        f"    {W(U(el[2]) if len(el)>2 else '',36)}  12B {W(c12[1][0],3)}              {R(c12[1][1],14)}",
        "",
        f" E  EMPLOYEE NAME                         13 STAT RET 3PSICK      [ ] [ ] [ ]",
        f"    {W(U(g(f,'first'))+' '+U(g(f,'last')),36)}  14 OTHER",
        f" F  {W(U(a[0]),36)}",
        f"    {W(U(a[1]),36)}",
        "-" * 78,
        f" 15 ST  EMPLOYER STATE ID   16 STATE WAGES    17 STATE TAX   18 LOCAL  19 TAX",
        f"    {W(g(f,'state1'),3)} {W(g(f,'stid1'),18)} {R(g(f,'sw1'),14)}  {R(g(f,'st1'),13)}",
        "-" * 78,
        " DEPT OF THE TREASURY - INTERNAL REVENUE SERVICE              OMB NO. 1545-0008",
    ]
    body = '<div class="paper"><pre>' + e("\n".join(lines)) + "</pre></div>"
    return doc("W2 PRINT", CSS7, body, "size: letter; margin: 0.6in;")


# ============================= 8. university portal, separate name fields
CSS8 = """
body { font-family: "Palatino Linotype", Palatino, "Book Antiqua", serif; font-size: 10pt; color: #111; }
.uni { border-bottom: 4px double #7a1f2b; padding-bottom: 6px; display: flex; justify-content: space-between; align-items: flex-end; }
.uni .n { font-size: 15pt; color: #7a1f2b; font-variant: small-caps; }
.year { background: #7a1f2b; color: #fff; text-align: center; font-size: 12pt; padding: 4px; margin: 10px 0; letter-spacing: 2px; }
table.kv { border-collapse: collapse; width: 100%; margin-bottom: 10px; }
table.kv td { padding: 3px 6px; border: 1px solid #bbb; }
table.kv td.k { background: #f7efe9; width: 34%; font-size: 9pt; }
h3 { font-size: 10.5pt; margin: 12px 0 4px; color: #7a1f2b; }
.amts { display: grid; grid-template-columns: repeat(3, 1fr); border: 1px solid #bbb; }
.amts div { padding: 5px 7px; border: 1px solid #ddd; }
.amts small { display: block; font-size: 7.5pt; color: #555; }
.footer { position: fixed; bottom: 0; left: 0; right: 0; font-size: 7.5pt; color: #666; border-top: 1px solid #ccc; padding-top: 3px; }
"""


def t08_university(f):
    a = addr(f)
    K = lambda k, v: f'<tr><td class="k">{k}</td><td>{v}</td></tr>'
    A = lambda k, v: f'<div><small>{k}</small>{v or "&nbsp;"}</div>'
    b12 = "".join(A(f"Box 12{s} (Code {e(c)})", e(v)) for s, c, v in box12(f))
    body = f"""<div class="uni"><div class="n">Office of Payroll Services</div><div>Employee Tax Forms &middot; W-2 Reprint</div></div>
<div class="year">TAX YEAR {e(year(f))}</div>
<h3>Employee Information</h3>
<table class="kv">{K("Last Name", e(g(f,'last')))}{K("First Name", e(g(f,'first')))}
{K("Social Security Number", e(g(f,'ssn')))}{K("Mailing Address Line 1", e(a[0]))}{K("City / State / ZIP", e(a[1]))}</table>
<h3>Wages and Withholding</h3>
<div class="amts">{A("Box 1 Wages, tips, other comp.", e(g(f,'w1')))}{A("Box 2 Federal income tax withheld", e(g(f,'w2')))}
{A("Box 3 Social security wages", e(g(f,'w3')))}{A("Box 4 Social security tax withheld", e(g(f,'w4')))}
{A("Box 5 Medicare wages and tips", e(g(f,'w5')))}{A("Box 6 Medicare tax withheld", e(g(f,'w6')))}
{b12}{A("Box 15 State", e(g(f,'state1')))}{A("Box 16 State wages", e(g(f,'sw1')))}{A("Box 17 State income tax", e(g(f,'st1')))}</div>
<h3>Employer Information</h3>
<table class="kv">{K("Employer", br(emp_lines(f)))}{K("Federal EIN", e(g(f,'ein')))}
{K("State Employer ID", e(g(f,'stid1')))}{K("Document Control No.", e(g(f,'control')))}</table>
<div class="footer">This reprint is provided for the employee's records. Questions regarding your W-2 should be directed to the Payroll Office.</div>"""
    return doc("W-2 Reprint", CSS8, body, "size: letter; margin: 0.6in 0.7in 0.8in;")


# ================== 9. small-business grid w/ dashed borders + paycheck stub
CSS9 = """
body { font-family: Tahoma, Verdana, sans-serif; font-size: 8pt; }
.w { border: 2px solid #000; }
.r { display: flex; }
.r > div { border: 1px dashed #666; flex: 1; padding: 2px 4px; min-height: 0.34in; }
.r > div .k { font-size: 6.5pt; color: #444; } .r > div .v { font-size: 9.5pt; font-weight: bold; }
.lbl { text-align: center; font-weight: bold; font-size: 9pt; margin: 2px 0 4px; }
.stub { margin-top: 0.45in; border-top: 2px dotted #000; padding-top: 10px; }
.stub table { width: 100%; border-collapse: collapse; font-size: 8pt; }
.stub th, .stub td { border: 1px solid #aaa; padding: 3px 5px; text-align: right; }
.stub th:first-child, .stub td:first-child { text-align: left; }
"""


def t09_smallbiz_stub(f):
    a = addr(f)
    D = lambda k, v, fl=1: f'<div style="flex:{fl}"><div class="k">{k}</div><div class="v">{v or "&nbsp;"}</div></div>'
    s12 = [b12_slot(f, i) for i in range(4)]
    s12h = "".join(D(f'12{"abcd"[i]}', f"{e(c)} {e(v)}") for i, (c, v) in enumerate(s12))
    body = f"""<div class="lbl">{e(year(f))} W-2 &nbsp; Copy C For EMPLOYEE'S RECORDS &nbsp; (Prepared with Ledgerly Payroll)</div>
<div class="w">
<div class="r">{D("a Employee's soc. sec. no.", e(g(f,'ssn')))}{D("b Employer ID no. (EIN)", e(g(f,'ein')))}{D("d Control number", e(g(f,'control')))}</div>
<div class="r">{D("c Employer's name, address, ZIP", br(emp_lines(f)), 2)}
<div style="flex:2;padding:0;border:none"><div class="r">{D("1 Wages", e(g(f,'w1')))}{D("2 Fed. tax withheld", e(g(f,'w2')))}</div>
<div class="r">{D("3 SS wages", e(g(f,'w3')))}{D("4 SS tax withheld", e(g(f,'w4')))}</div>
<div class="r">{D("5 Medicare wages", e(g(f,'w5')))}{D("6 Medicare tax", e(g(f,'w6')))}</div></div></div>
<div class="r">{D("e Employee's name", e(g(f,'first')) + " " + e(g(f,'last')), 2)}{D("7 SS tips","")}{D("8 Allocated tips","")}</div>
<div class="r">{D("f Employee's address and ZIP", e(a[0]) + "<br>" + e(a[1]), 2)}{D("10 Dep. care","")}{D("11 Nonqual. plans","")}</div>
<div class="r">{s12h}</div>
<div class="r">{D("15 State", e(g(f,'state1')), 0.5)}{D("Employer's state ID", e(g(f,'stid1')), 1.3)}{D("16 State wages", e(g(f,'sw1')))}{D("17 State tax", e(g(f,'st1')))}{D("18 Local wages","")}{D("19 Local tax","")}{D("20 Locality","")}</div>
</div>
<div class="stub"><b>Year-End Earnings Summary &mdash; {e(year(f))}</b> &nbsp; (detach and retain)
<table><tr><th>Item</th><th>Year-to-date</th><th>W-2 Box</th></tr>
<tr><td>Federal taxable wages</td><td>{e(g(f,'w1'))}</td><td>1</td></tr>
<tr><td>Federal income tax</td><td>{e(g(f,'w2'))}</td><td>2</td></tr>
<tr><td>Social security tax</td><td>{e(g(f,'w4'))}</td><td>4</td></tr>
<tr><td>Medicare tax</td><td>{e(g(f,'w6'))}</td><td>6</td></tr>
<tr><td>{e(g(f,'state1'))} state income tax</td><td>{e(g(f,'st1'))}</td><td>17</td></tr></table></div>"""
    return doc("W-2 Copy C", CSS9, body)


# ========================== 10. tax-preparer software input worksheet
CSS10 = """
body { font-family: Arial, sans-serif; font-size: 8.5pt; }
.bar { background: #dfe6ee; border: 1px solid #8aa; padding: 4px 8px; display: flex; justify-content: space-between; font-weight: bold; }
.sec { margin-top: 8px; border: 1px solid #8aa; }
.sec .t { background: #eef2f6; padding: 3px 8px; font-weight: bold; border-bottom: 1px solid #8aa; }
.line { display: grid; grid-template-columns: 40px 1fr 170px; align-items: center; border-bottom: 1px dotted #aab; padding: 2px 8px; }
.line .no { font-weight: bold; }
.line .in { border: 1px solid #889; background: #fffbe6; padding: 2px 5px; font-family: "Courier New", monospace; min-height: 16px; }
.line.wide { grid-template-columns: 40px 160px 1fr; }
.p { font-size: 7pt; color: #555; margin-top: 6px; }
"""


def t10_preparer_worksheet(f):
    a = addr(f)
    L = lambda n, l, v, w=False: (f'<div class="line{" wide" if w else ""}"><span class="no">{n}</span>'
                                  f'<span>{l}</span><span class="in">{v or "&nbsp;"}</span></div>')
    b12 = "".join(L(f"12{s}", f"Code {e(c)}", e(v)) for s, c, v in box12(f))
    el = emp_lines(f)
    body = f"""<div class="bar"><span>W-2 Wage and Tax Statement &mdash; Input Worksheet</span><span>{e(year(f))} &nbsp; Client copy</span></div>
<div class="sec"><div class="t">Employee</div>
{L("a", "Employee's SSN", e(g(f,'ssn')), True)}
{L("e", "First name", e(g(f,'first')), True)}{L("", "Last name", e(g(f,'last')), True)}
{L("f", "Street address", e(a[0]), True)}{L("", "City, state, ZIP", e(a[1]), True)}</div>
<div class="sec"><div class="t">Employer</div>
{L("b", "EIN", e(g(f,'ein')), True)}{L("c", "Name", e(el[0]), True)}
{L("", "Street", e(el[1] if len(el)>1 else ''), True)}{L("", "City, state, ZIP", e(el[2] if len(el)>2 else ''), True)}
{L("d", "Control number", e(g(f,'control')), True)}</div>
<div class="sec"><div class="t">Wages and Withholding</div>
{L("1", "Wages, tips, other compensation", e(g(f,'w1')))}{L("2", "Federal income tax withheld", e(g(f,'w2')))}
{L("3", "Social security wages", e(g(f,'w3')))}{L("4", "Social security tax withheld", e(g(f,'w4')))}
{L("5", "Medicare wages and tips", e(g(f,'w5')))}{L("6", "Medicare tax withheld", e(g(f,'w6')))}
{L("7", "Social security tips", "")}{L("8", "Allocated tips", "")}{L("10", "Dependent care benefits", "")}{b12}</div>
<div class="sec"><div class="t">State and Local</div>
{L("15", "State", e(g(f,'state1')))}{L("15", "Employer's state ID number", e(g(f,'stid1')))}
{L("16", "State wages, tips, etc.", e(g(f,'sw1')))}{L("17", "State income tax", e(g(f,'st1')))}
{L("18", "Local wages", "")}{L("19", "Local income tax", "")}{L("20", "Locality name", "")}</div>
<div class="p">Worksheet printed for review. Not a substitute for the employer-issued Form W-2.</div>"""
    return doc("W-2 Input Worksheet", CSS10, body)


# ======================================= 11. four-up (4 copies per page)
CSS11 = """
body { font-family: Arial, Helvetica, sans-serif; font-size: 6.5pt; }
.sheet { display: grid; grid-template-columns: 1fr 1fr; grid-template-rows: 1fr 1fr; height: 10in; gap: 0; }
.q { border: 1px dashed #888; padding: 8px; }
.q table { width: 100%; border-collapse: collapse; table-layout: fixed; }
.q td { border: 0.5pt solid #000; padding: 1px 3px; vertical-align: top; height: 0.33in; }
.q td span { display: block; font-size: 5.5pt; }
.q td b { font-size: 7pt; white-space: nowrap; font-weight: normal; font-family: "Courier New", monospace; }
.q .ttl { display: flex; justify-content: space-between; font-size: 7pt; margin-bottom: 2px; }
.q .ttl b { font-size: 10pt; }
.q .cp { font-size: 6pt; margin-top: 2px; }
"""


def _quad(f, cp):
    a = addr(f)
    c12 = [b12_slot(f, i) for i in range(2)]
    T = lambda cap, v, cs=1: f'<td colspan="{cs}"><span>{cap}</span><b>{v}</b></td>'
    return f"""<div class="q"><div class="ttl"><span>Form <b>W-2</b> Wage and Tax Statement</span><b>{e(year(f))}</b></div>
<table><colgroup><col style="width:46%"><col style="width:27%"><col style="width:27%"></colgroup>
<tr>{T("a Employee's SSN", e(g(f,'ssn')))}{T("1 Wages, tips, other comp.", e(g(f,'w1')))}{T("2 Federal income tax withheld", e(g(f,'w2')))}</tr>
<tr>{T("b Employer ID number (EIN)", e(g(f,'ein')))}{T("3 Social security wages", e(g(f,'w3')))}{T("4 Social security tax withheld", e(g(f,'w4')))}</tr>
<tr><td rowspan="2"><span>c Employer's name, address, and ZIP code</span><b>{br(emp_lines(f))}</b></td>{T("5 Medicare wages and tips", e(g(f,'w5')))}{T("6 Medicare tax withheld", e(g(f,'w6')))}</tr>
<tr>{T("7 Social security tips", "")}{T("8 Allocated tips", "")}</tr>
<tr>{T("d Control number", e(g(f,'control')))}{T("10 Dependent care benefits", "")}{T("11 Nonqualified plans", "")}</tr>
<tr><td rowspan="2"><span>e Employee's name, address, and ZIP code</span><b>{e(g(f,'first'))} {e(g(f,'last'))}<br>{e(a[0])}<br>{e(a[1])}</b></td>
{T("12a", e(c12[0][0]) + " " + e(c12[0][1]))}{T("12b", e(c12[1][0]) + " " + e(c12[1][1]))}</tr>
<tr>{T("13 Stat / Ret / 3PSP", "")}{T("14 Other", "")}</tr>
<tr>{T("15 State &nbsp; Employer's state ID no.", e(g(f,'state1')) + " " + e(g(f,'stid1')))}{T("16 State wages, tips, etc.", e(g(f,'sw1')))}{T("17 State income tax", e(g(f,'st1')))}</tr>
<tr>{T("18 Local wages, tips, etc.", "")}{T("19 Local income tax", "")}{T("20 Locality name", "")}</tr>
</table><div class="cp">{cp}</div></div>"""


def t11_four_up(f):
    cps = ["Copy B To Be Filed With Employee's FEDERAL Tax Return.",
           "Copy C For EMPLOYEE'S RECORDS.",
           "Copy 2 To Be Filed With Employee's State, City, or Local Income Tax Return.",
           "Copy 2 To Be Filed With Employee's State, City, or Local Income Tax Return."]
    body = '<div class="sheet">' + "".join(_quad(f, c) for c in cps) + "</div>"
    return doc("W-2 4-up", CSS11, body, "size: letter; margin: 0.4in;")


# ===================== 12. government agency notice, masked SSN, ALL CAPS
CSS12 = """
body { font-family: "Arial Narrow", Arial, sans-serif; font-size: 9pt; }
.agency { text-align: center; border: 2px solid #000; padding: 6px; }
.agency .a { font-size: 11pt; font-weight: bold; letter-spacing: 1px; }
table { width: 100%; border-collapse: collapse; margin-top: 8px; }
td, th { border: 1px solid #000; padding: 3px 5px; }
th { background: #d9d9d9; font-size: 8pt; text-align: left; }
td.n { text-align: right; }
.mail { margin: 14px 0 0 0.4in; width: 3.6in; border: 1px solid #000; padding: 8px; font-size: 10pt; text-transform: uppercase; }
.small { font-size: 7.5pt; margin-top: 10px; }
"""


def t12_gov_masked(f):
    a = addr(f)
    U = lambda s: e((s or "").upper())
    b12 = "".join(f'<tr><td>12{s}</td><td>CODE {U(c)}</td><td class="n">{e(v)}</td></tr>' for s, c, v in box12(f))
    body = f"""<div class="agency"><div class="a">STATE PAYROLL SERVICES DIVISION</div>
<div>EMPLOYEE W-2 STATEMENT &mdash; TAX YEAR {e(year(f))} &mdash; DUPLICATE</div></div>
<div class="mail">{U(g(f,'first'))} {U(g(f,'last'))}<br>{U(a[0])}<br>{U(a[1])}</div>
<table><tr><th>EMPLOYEE SSN</th><th>EMPLOYER EIN</th><th>CONTROL NO.</th><th>STATE / EMPLOYER STATE ID</th></tr>
<tr><td>{e(mask(g(f,'ssn')))}</td><td>{e(g(f,'ein'))}</td><td>{e(g(f,'control'))}</td><td>{e(g(f,'state1'))} {e(g(f,'stid1'))}</td></tr></table>
<table><tr><th colspan="3">EMPLOYER</th></tr><tr><td colspan="3">{"<br>".join(U(l) for l in emp_lines(f))}</td></tr></table>
<table><tr><th style="width:10%">BOX</th><th>ITEM</th><th style="width:30%">AMOUNT</th></tr>
<tr><td>1</td><td>WAGES, TIPS, OTHER COMPENSATION</td><td class="n">{e(g(f,'w1'))}</td></tr>
<tr><td>2</td><td>FEDERAL INCOME TAX WITHHELD</td><td class="n">{e(g(f,'w2'))}</td></tr>
<tr><td>3</td><td>SOCIAL SECURITY WAGES</td><td class="n">{e(g(f,'w3'))}</td></tr>
<tr><td>4</td><td>SOCIAL SECURITY TAX WITHHELD</td><td class="n">{e(g(f,'w4'))}</td></tr>
<tr><td>5</td><td>MEDICARE WAGES AND TIPS</td><td class="n">{e(g(f,'w5'))}</td></tr>
<tr><td>6</td><td>MEDICARE TAX WITHHELD</td><td class="n">{e(g(f,'w6'))}</td></tr>{b12}
<tr><td>16</td><td>STATE WAGES, TIPS, ETC.</td><td class="n">{e(g(f,'sw1'))}</td></tr>
<tr><td>17</td><td>STATE INCOME TAX</td><td class="n">{e(g(f,'st1'))}</td></tr></table>
<div class="small">THIS DUPLICATE IS ISSUED AT THE EMPLOYEE'S REQUEST. SSN TRUNCATED IN ACCORDANCE WITH TREAS. REG. 31.6051-1.
THE ORIGINAL STATEMENT FILED WITH THE SOCIAL SECURITY ADMINISTRATION CONTAINS THE COMPLETE NUMBER.</div>"""
    return doc("W-2 Duplicate", CSS12, body, "size: letter; margin: 0.6in;")


# ================================== 13. modern two-column federal/state cards
CSS13 = """
body { font-family: "Helvetica Neue", Helvetica, Arial, sans-serif; font-size: 9pt; color: #20252b; }
.top { display: flex; justify-content: space-between; align-items: center; }
.brand { font-size: 12pt; font-weight: 700; color: #e05a2b; }
.who { margin-top: 10px; display: grid; grid-template-columns: 1fr 1fr; gap: 14px; background: #fafafa; border: 1px solid #eee; padding: 10px; }
.who .k { font-size: 7.5pt; color: #8a8f96; text-transform: uppercase; letter-spacing: .4px; }
.cols { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-top: 14px; }
.col { border-top: 3px solid #e05a2b; }
.col h4 { margin: 6px 0; font-size: 10pt; }
.it { display: flex; justify-content: space-between; border-bottom: 1px solid #f0f0f0; padding: 4px 0; }
.it em { font-style: normal; color: #6b7178; }
.it b { font-variant-numeric: tabular-nums; }
.fine { margin-top: 18px; font-size: 7.5pt; color: #8a8f96; }
"""


def t13_two_col_modern(f):
    a = addr(f)
    I = lambda k, v: f'<div class="it"><em>{k}</em><b>{v or "&mdash;"}</b></div>'
    b12 = "".join(I(f"Box 12{s} &middot; {e(c)}", e(v)) for s, c, v in box12(f))
    body = f"""<div class="top"><span class="brand">Tandem Payroll</span><span>Your {e(year(f))} W-2 &middot; Wage and Tax Statement</span></div>
<div class="who"><div><div class="k">Employee</div><b>{e(g(f,'first'))} {e(g(f,'last'))}</b><br>{e(a[0])}<br>{e(a[1])}
<div class="k" style="margin-top:6px">SSN</div>{e(g(f,'ssn'))}</div>
<div><div class="k">Employer</div>{br(emp_lines(f))}<div class="k" style="margin-top:6px">EIN &middot; Control #</div>{e(g(f,'ein'))} &middot; {e(g(f,'control')) or "&mdash;"}</div></div>
<div class="cols"><div class="col"><h4>Federal</h4>
{I("Wages, tips, other comp. (1)", e(g(f,'w1')))}{I("Federal income tax withheld (2)", e(g(f,'w2')))}
{I("Social security wages (3)", e(g(f,'w3')))}{I("Social security tax withheld (4)", e(g(f,'w4')))}
{I("Medicare wages and tips (5)", e(g(f,'w5')))}{I("Medicare tax withheld (6)", e(g(f,'w6')))}{b12}</div>
<div class="col"><h4>State &mdash; {e(g(f,'state1'))}</h4>
{I("Employer state ID (15)", e(g(f,'stid1')))}{I("State wages, tips, etc. (16)", e(g(f,'sw1')))}
{I("State income tax (17)", e(g(f,'st1')))}{I("Local wages (18)", "")}{I("Local income tax (19)", "")}{I("Locality (20)", "")}</div></div>
<div class="fine">Copy B &mdash; To be filed with employee's federal tax return. Copy 2 &mdash; To be filed with employee's state, city, or local income tax return.
Copy C &mdash; For employee's records. This information is being furnished to the IRS.</div>"""
    return doc("Your W-2", CSS13, body, "size: letter; margin: 0.6in;")


# ========== 14. enterprise portal: IRS grid on top half + notice stub (masked? no)
CSS14 = """
body { font-family: Cambria, Georgia, serif; font-size: 8pt; }
.ph { display: flex; justify-content: space-between; border-bottom: 1px solid #000; padding-bottom: 3px; margin-bottom: 6px; font-family: Arial, sans-serif; font-size: 7.5pt; }
.box { display: grid; grid-template-columns: 2fr 1fr 1fr; border: 2px solid #000; }
.box > div { border: 0.5pt solid #000; padding: 2px 4px; min-height: 0.36in; }
.box .c { font-size: 6pt; font-family: Arial, sans-serif; }
.box .v { font-size: 10pt; font-weight: bold; text-align: right; }
.box .v.l { text-align: left; font-weight: normal; }
.st { display: grid; grid-template-columns: 0.5fr 1.5fr 1fr 1fr 1fr 1fr 1fr; border: 2px solid #000; border-top: none; }
.st > div { border: 0.5pt solid #000; padding: 2px 4px; min-height: 0.36in; }
.st .c { font-size: 6pt; font-family: Arial, sans-serif; } .st .v { font-size: 10pt; font-weight: bold; text-align: right; }
.notice { margin-top: 0.4in; border: 1px solid #000; padding: 8px 10px; font-size: 8pt; }
.notice h4 { margin: 0 0 4px; font-size: 9pt; }
.addr { margin-top: 10px; font-family: "Courier New", monospace; font-size: 10pt; }
.pg { position: fixed; bottom: 0; right: 0; font-size: 7pt; font-family: Arial, sans-serif; }
"""


def t14_portal_notice(f):
    a = addr(f)
    C = lambda c, v, l=False: f'<div><div class="c">{c}</div><div class="v{" l" if l else ""}">{v or "&nbsp;"}</div></div>'
    s12 = [b12_slot(f, i) for i in range(4)]
    S = lambda i: C(f'12{"abcd"[i]} Code &nbsp; Amount', (e(s12[i][0]) + " &nbsp; " + e(s12[i][1])) if s12[i][0] else "")
    body = f"""<div class="ph"><span>Workforce Portal &rsaquo; Pay &rsaquo; Tax Documents</span><span>Form W-2 {e(year(f))} &mdash; Employee Copy B / C / 2</span></div>
<div class="box">
{C("e Employee's name (Last, First)", e(g(f,'last').upper()) + ", " + e(g(f,'first').upper()), True)}{C("1 Wages, tips, other compensation", e(g(f,'w1')))}{C("2 Federal income tax withheld", e(g(f,'w2')))}
{C("f Employee's address and ZIP code", e(a[0]) + ", " + e(a[1]), True)}{C("3 Social security wages", e(g(f,'w3')))}{C("4 Social security tax withheld", e(g(f,'w4')))}
{C("a Employee's social security number", e(g(f,'ssn')), True)}{C("5 Medicare wages and tips", e(g(f,'w5')))}{C("6 Medicare tax withheld", e(g(f,'w6')))}
{C("b Employer identification number (EIN)", e(g(f,'ein')), True)}{S(0)}{S(1)}
{C("c Employer's name, address, and ZIP code", br(emp_lines(f)), True)}{S(2)}{S(3)}
{C("d Control number", e(g(f,'control')), True)}{C("13 Retirement plan", "", True)}{C("14 Other", "", True)}
</div>
<div class="st">{C("15 State", e(g(f,'state1')))}{C("Employer's state ID number", e(g(f,'stid1')))}{C("16 State wages", e(g(f,'sw1')))}
{C("17 State income tax", e(g(f,'st1')))}{C("18 Local wages", "")}{C("19 Local income tax", "")}{C("20 Locality name", "")}</div>
<div class="notice"><h4>Notice to Employee</h4>
Keep Copy C of this Form W-2 for at least 3 years after the due date for filing your income tax return. See the back of Copy B for
an explanation of the codes shown in box 12. If your name, SSN, or address is incorrect, contact
your HR representative.
<div class="addr">{e(g(f,'first'))} {e(g(f,'last'))}<br>{e(a[0])}<br>{e(a[1])}</div></div>
<div class="pg">Page 1 of 1</div>"""
    return doc("Form W-2", CSS14, body, "size: letter; margin: 0.5in;")


TEMPLATES = [
    t01_irs_grid_classic, t02_irs_two_copies, t03_gray_band_caps, t04_statement_lr,
    t05_cards_masked, t06_box_table, t07_line_printer, t08_university,
    t09_smallbiz_stub, t10_preparer_worksheet, t11_four_up, t12_gov_masked,
    t13_two_col_modern, t14_portal_notice,
]
