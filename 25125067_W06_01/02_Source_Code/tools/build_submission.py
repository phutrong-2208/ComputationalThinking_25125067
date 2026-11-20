"""Build the submitted PDFs and a captioned video from real browser screenshots.

Optional tooling: reportlab, Pillow, ffmpeg. Windows Arial/Consolas fonts.
This script does not automate a browser, create Git history, or make API calls.
"""
from html import escape
from pathlib import Path
import re
import shutil
import subprocess
import textwrap

from PIL import Image as PILImage, ImageDraw, ImageFont
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, XPreformatted

ROOT = Path(__file__).resolve().parents[2]
FONTS = Path("C:/Windows/Fonts")
TEMP = ROOT.parent / "tmp/lab06_build"


def inline(text):
    text = escape(text)
    text = re.sub(r"\[([^]]+)\]\(([^)]+)\)", r'<link href="\2" color="#5147c8">\1</link>', text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    return re.sub(r"`([^`]+)`", r'<font name="Code">\1</font>', text)


def make_pdf(source, output):
    pdfmetrics.registerFont(TTFont("Body", str(FONTS/"arial.ttf")))
    pdfmetrics.registerFont(TTFont("Bold", str(FONTS/"arialbd.ttf")))
    pdfmetrics.registerFont(TTFont("Code", str(FONTS/"consola.ttf")))
    pdfmetrics.registerFontFamily("Body", normal="Body", bold="Bold", italic="Body", boldItalic="Bold")
    width = A4[0]-88
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("VNBody",fontName="Body",fontSize=10,leading=15,spaceAfter=7,textColor=colors.HexColor("#34344b")))
    styles.add(ParagraphStyle("VNTitle",fontName="Bold",fontSize=24,leading=30,spaceAfter=18,textColor=colors.HexColor("#4139a0")))
    styles.add(ParagraphStyle("VNH1",fontName="Bold",fontSize=15,leading=20,spaceBefore=15,spaceAfter=8,keepWithNext=True,textColor=colors.HexColor("#4139a0")))
    styles.add(ParagraphStyle("VNH2",fontName="Bold",fontSize=11.5,leading=17,spaceBefore=10,spaceAfter=6,keepWithNext=True,textColor=colors.HexColor("#313149")))
    styles.add(ParagraphStyle("VNCode",fontName="Code",fontSize=8.2,leading=11.8,backColor=colors.HexColor("#f2f2fa"),borderPadding=9,spaceBefore=5,spaceAfter=12))
    styles.add(ParagraphStyle("VNCell",fontName="Body",fontSize=9,leading=13,spaceAfter=0,splitLongWords=True))
    styles.add(ParagraphStyle("VNCaption",parent=styles["VNBody"],fontSize=8.5,leading=12,alignment=TA_CENTER,textColor=colors.HexColor("#77728a")))
    lines=source.read_text(encoding="utf-8").splitlines();story=[];i=0
    while i<len(lines):
        line=lines[i].strip()
        if not line:
            i+=1;continue
        if line.startswith("```"):
            code=[];i+=1
            while i<len(lines) and not lines[i].strip().startswith("```"):
                code.extend(textwrap.wrap(lines[i],width=92,replace_whitespace=False,drop_whitespace=False) or [""]);i+=1
            story.append(XPreformatted(escape("\n".join(code)),styles["VNCode"]));i+=1;continue
        if line.startswith("|"):
            rows=[]
            while i<len(lines) and lines[i].strip().startswith("|"):
                cells=[c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r"[: -]+",c) for c in cells): rows.append(cells)
                i+=1
            data=[[Paragraph(inline(c),styles["VNCell"]) for c in row] for row in rows]
            col_widths=[width*.32,width*.68] if len(rows[0])==2 else [width/len(rows[0])]*len(rows[0])
            table=Table(data,colWidths=col_widths,repeatRows=1,hAlign="LEFT")
            table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#eeecfb")),("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#fafafe")]),("VALIGN",(0,0),(-1,-1),"TOP"),("BOX",(0,0),(-1,-1),.5,colors.HexColor("#dedbea")),("INNERGRID",(0,0),(-1,-1),.3,colors.HexColor("#e8e5f0")),("LEFTPADDING",(0,0),(-1,-1),9),("RIGHTPADDING",(0,0),(-1,-1),9),("TOPPADDING",(0,0),(-1,-1),8),("BOTTOMPADDING",(0,0),(-1,-1),8)]))
            story.extend([table,Spacer(1,10)]);continue
        image=re.fullmatch(r"!\[([^]]*)\]\(([^)]+)\)",line)
        if image:
            path=(source.parent/image[2]).resolve()
            with PILImage.open(path) as im: iw,ih=im.size
            scale=min(290/iw,320/ih)
            story.extend([Spacer(1,8),Image(str(path),width=iw*scale,height=ih*scale),Spacer(1,7),Paragraph(inline(image[1]),styles["VNCaption"])]);i+=1;continue
        if line.startswith("#"):
            level=len(line)-len(line.lstrip("#"))
            story.append(Paragraph(inline(line[level:].strip()),styles["VNTitle" if level==1 else "VNH1" if level==2 else "VNH2"]));i+=1;continue
        bullet=line.startswith("- ")
        chunks=[line[2:] if bullet else line];i+=1
        while i<len(lines) and lines[i].strip() and not re.match(r"^(#|\||```|!\[|- |\d+\. )",lines[i].strip()):
            chunks.append(lines[i].strip());i+=1
        story.append(Paragraph(inline(" ".join(chunks)),styles["VNBody"],bulletText="•" if bullet else None))

    def footer(canvas,doc):
        canvas.saveState();canvas.setStrokeColor(colors.HexColor("#dedbea"));canvas.line(44,37,A4[0]-44,37)
        canvas.setFont("Body",8);canvas.setFillColor(colors.HexColor("#817891"))
        canvas.drawString(44,24,"25125067 · Lab06 · StudySpot")
        canvas.drawRightString(A4[0]-44,24,f"Page {doc.page}");canvas.restoreState()
    doc=SimpleDocTemplate(str(output),pagesize=A4,leftMargin=44,rightMargin=44,topMargin=42,bottomMargin=52,title="25125067 - Lab06 - StudySpot",author="25125067")
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    print("PDF:",output.relative_to(ROOT))


SCENES = [
    ("01_home.jpg","Một góc nhỏ, nhiều ý tưởng.","StudySpot giúp tìm quán cà phê và thư viện bằng OpenStreetMap API.\n\nMSSV 25125067 · Lab06\n\nVideo dựng từ ảnh chụp thao tác thật, không phải quay màn hình liên tục."),
    ("02_live_results.jpg","24 địa điểm từ API thật.","Tâm: Nhà thờ Đức Bà, TP.HCM.\nBán kính: 300 m.\n\nServer lấy dữ liệu OSM, lọc amenity và tính khoảng cách đường chim bay. Dữ liệu thiếu được ghi rõ."),
    ("03_wifi_filter.jpg","Thu hẹp lựa chọn.","Bật “Có Wi-Fi”: danh sách còn 6 địa điểm.\n\nBộ lọc chạy trên dữ liệu đã tải, không tạo thêm truy vấn API. Có thẻ Wi-Fi không bảo đảm quán phù hợp để học."),
    ("04_place_details.jpg","Xem thông tin cần thiết.","Cà Phê Au Parc: cách tâm truy vấn 151 m.\n\nĐịa chỉ, Wi-Fi, giờ mở cửa và mức tiếp cận xe lăn được đọc từ các thẻ OSM. Có liên kết đến đối tượng gốc."),
    ("05_saved_place.jpg","Lưu một nơi để quay lại.","Nhấn Lưu địa điểm.\n\nNút đổi thành Bỏ lưu địa điểm. Thông tin được lưu trên trình duyệt bằng localStorage, không cần tài khoản."),
    ("08_saved_after_reload.jpg","Tải lại vẫn còn địa điểm.","Sau reload, mục Đã lưu vẫn có Cà Phê Au Parc.\n\nDữ liệu không đồng bộ giữa các máy. Xóa dữ liệu trình duyệt sẽ làm mất danh sách đã lưu."),
    ("06_export.jpg","Mang dữ liệu theo bạn.","Xuất danh sách đang hiển thị thành GeoJSON.\n\nTọa độ theo thứ tự kinh độ, vĩ độ; giữ nguồn OSM và ODbL. File mẫu được tạo bằng chính hàm xuất từ phản hồi API đã lưu."),
    ("07_api_integration.jpg","Đối chiếu cách tích hợp.","Mục Về StudySpot hiển thị endpoint, vùng bbox, thời điểm lấy và số kết quả.\n\nAPI v0.6 chỉ đọc; kết quả không phải dữ liệu do AI tự tạo."),
    ("09_empty_filter.jpg","Không có kết quả cũng rõ ràng.","Lọc một tên không tồn tại: danh sách rỗng và có hướng dẫn bỏ bộ lọc.\n\nCó xử lý lỗi mạng, đầu vào sai và timeout. Mã nguồn, báo cáo và kiểm thử đi kèm bộ bài."),
]


def wrapped(text,font,width,draw):
    result=[]
    for paragraph in text.split("\n"):
        if not paragraph:
            result.append("");continue
        line=""
        for word in paragraph.split():
            trial=(line+" "+word).strip()
            if draw.textlength(trial,font=font)>width and line:
                result.append(line);line=word
            else:line=trial
        result.append(line)
    return result


def make_video():
    frames=TEMP/"video_frames";frames.mkdir(parents=True,exist_ok=True)
    titlefont=ImageFont.truetype(str(FONTS/"arialbd.ttf"),55)
    bodyfont=ImageFont.truetype(str(FONTS/"arial.ttf"),33)
    label=ImageFont.truetype(str(FONTS/"arialbd.ttf"),22)
    small=ImageFont.truetype(str(FONTS/"arial.ttf"),21)
    subtitles=[]
    for index,(filename,title,body) in enumerate(SCENES):
        canvas=PILImage.new("RGB",(1920,1080),"#17162f");draw=ImageDraw.Draw(canvas)
        draw.rounded_rectangle((42,83,889,993),radius=20,fill="#ffffff")
        screenshot=PILImage.open(ROOT/"03_Demo"/filename).convert("RGB")
        if filename=="02_live_results.jpg":
            # Crop only the viewport area containing results; never alter UI text/data.
            screenshot=screenshot.crop((0,screenshot.height-680,screenshot.width,screenshot.height))
        screenshot.thumbnail((807,870),PILImage.Resampling.LANCZOS)
        canvas.paste(screenshot,(465-screenshot.width//2,538-screenshot.height//2))
        draw.text((51,35),"STUDYSPOT  /  LAB06  /  25125067",font=label,fill="#c9c3ff")
        draw.rounded_rectangle((970,115,1060,122),radius=3,fill="#9ee6c3")
        y=160
        for line in wrapped(title,titlefont,835,draw):
            draw.text((967,y),line,font=titlefont,fill="white");y+=72
        y+=26
        for line in wrapped(body,bodyfont,825,draw):
            draw.text((970,y),line,font=bodyfont,fill="#cecbdf");y+=46
        draw.text((970,939),f"{index+1:02d} / {len(SCENES):02d}",font=label,fill="#a49adb")
        draw.text((51,1030),"Ảnh thao tác thật · OpenStreetMap contributors / ODbL · 20/11/2026",font=small,fill="#a8a0c1")
        frame=frames/f"scene_{index:02d}.png";canvas.save(frame)
        def stamp(seconds):return f"00:{seconds//60:02d}:{seconds%60:02d},000"
        subtitles.append(f"{index+1}\n{stamp(index*10)} --> {stamp((index+1)*10)}\n{title}\n"+body.replace("\n\n","\n")+"\n")
    concat=frames/"frames.txt"
    listing=[]
    for index in range(len(SCENES)):
        listing.extend([f"file 'scene_{index:02d}.png'","duration 10"])
    listing.append(f"file 'scene_{len(SCENES)-1:02d}.png'")
    concat.write_text("\n".join(listing),encoding="utf-8")
    (ROOT/"03_Demo/Demo.srt").write_text("\n".join(subtitles),encoding="utf-8")
    command=[shutil.which("ffmpeg") or "ffmpeg","-y","-hide_banner","-loglevel","error","-f","concat","-safe","0","-i",str(concat),"-t",str(len(SCENES)*10),"-vf","fps=25","-c:v","libx264","-preset","medium","-crf","20","-pix_fmt","yuv420p","-movflags","+faststart",str(ROOT/"03_Demo/Demo.mp4")]
    subprocess.run(command,check=True)
    print("Video:","03_Demo/Demo.mp4",f"({len(SCENES)*10} seconds, 1920x1080)")


if __name__=="__main__":
    TEMP.mkdir(parents=True,exist_ok=True)
    make_pdf(ROOT/"01_Documentation/Report.md",ROOT/"01_Documentation/Report.pdf")
    make_pdf(ROOT/"README.md",ROOT/"README.pdf")
    make_video()
