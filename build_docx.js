const { Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
        AlignmentType, WidthType, BorderStyle, ShadingType } = require('docx');
const fs = require('fs');

const data = JSON.parse(fs.readFileSync('cv_data.json', 'utf8'));

const DARK = "1F2D3D";
const ACCENT = "2E75B6";
const LIGHT_GREY = "F2F2F2";
const FONT = "Calibri";

const border = { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" };
const borders = { top: border, bottom: border, left: border, right: border };

function spacer() {
    return new Paragraph({ spacing: { before: 120, after: 0 }, children: [] });
}

function para(text, opts = {}) {
    return new Paragraph({
        alignment: opts.align || AlignmentType.LEFT,
        spacing: { before: opts.spaceBefore || 0, after: opts.spaceAfter || 60 },
        children: [new TextRun({
            text: text,
            bold: opts.bold || false,
            size: opts.size || 17,
            color: opts.color || DARK,
            font: FONT
        })]
    });
}

function sectionHeading(text) {
    return new Paragraph({
        spacing: { before: 200, after: 100 },
        border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: ACCENT, space: 1 } },
        children: [new TextRun({
            text: text,
            bold: true,
            size: 20,
            color: ACCENT,
            font: FONT
        })]
    });
}

function bulletPara(text) {
    return new Paragraph({
        spacing: { before: 30, after: 30 },
        indent: { left: 360, hanging: 180 },
        children: [
            new TextRun({ text: "\u2022 ", bold: true, size: 17, color: ACCENT, font: FONT }),
            new TextRun({ text: text, size: 17, color: DARK, font: FONT })
        ]
    });
}

function twoColTable(rows) {
    return new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [2800, 6560],
        rows: rows.map(row => new TableRow({
            children: [
                new TableCell({
                    borders,
                    width: { size: 2800, type: WidthType.DXA },
                    shading: { fill: LIGHT_GREY, type: ShadingType.CLEAR },
                    margins: { top: 80, bottom: 80, left: 120, right: 120 },
                    children: [new Paragraph({
                        children: [new TextRun({
                            text: row[0] || '',
                            bold: true,
                            size: 17,
                            font: FONT,
                            color: DARK
                        })]
                    })]
                }),
                new TableCell({
                    borders,
                    width: { size: 6560, type: WidthType.DXA },
                    margins: { top: 80, bottom: 80, left: 120, right: 120 },
                    children: [new Paragraph({
                        children: [new TextRun({
                            text: row[1] || '',
                            size: 17,
                            font: FONT,
                            color: DARK
                        })]
                    })]
                })
            ]
        }))
    });
}

function isDateLine(line) {
    return /\d{4}\s*[–\-]\s*(Present|\d{4})/.test(line) ||
           /\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}/.test(line);
}

function isCompanyLine(line) {
    return line.includes(' | ') && isDateLine(line);
}

function isJobTitle(line) {
    // Explicitly catch Earlier Career block
    if (line.startsWith('Earlier Career') || line.startsWith('Earlier Experience')) return true;
    // Job title: no bullet, no pipe separator with date
    return !line.startsWith('•') &&
           !line.startsWith('-') &&
           !isCompanyLine(line);
}

function isPlaceholder(text) {
    const t = text.replace(/^[•\-]\s*/, '').trim();
    return t === '--' || t === '' || t === '-';
}

const children = [];

// --- HEADER ---
children.push(new Paragraph({
    spacing: { before: 0, after: 60 },
    children: [new TextRun({
        text: data.header[0],
        bold: true,
        size: 52,
        color: DARK,
        font: FONT
    })]
}));

if (data.header[1]) {
    children.push(new Paragraph({
        spacing: { before: 0, after: 40 },
        children: [new TextRun({
            text: data.header[1],
            size: 19,
            color: "444444",
            font: FONT
        })]
    }));
}

data.header.slice(2).forEach(line => {
    children.push(para(line, { size: 17, color: "555555", spaceAfter: 30 }));
});

children.push(spacer());

// --- PROFESSIONAL SUMMARY ---
children.push(sectionHeading("PROFESSIONAL SUMMARY"));
children.push(para(data.professional_summary, { size: 17, spaceAfter: 80 }));

// --- CORE COMPETENCIES ---
children.push(sectionHeading("CORE COMPETENCIES"));
if (data.tables.core_competencies) {
    children.push(twoColTable(data.tables.core_competencies));
}
children.push(spacer());

// --- PROFESSIONAL EXPERIENCE ---
children.push(sectionHeading("PROFESSIONAL EXPERIENCE"));

let isFirstJob = true;

data.professional_experience.forEach(line => {
    const trimmed = line.trim();
    if (!trimmed) return;
    if (isPlaceholder(trimmed)) return;

    if (trimmed.startsWith('•') || trimmed.startsWith('-')) {
        // Bullet point
        const bulletText = trimmed.replace(/^[•\-]\s*/, '').trim();
        if (bulletText && !isPlaceholder(bulletText)) {
            children.push(bulletPara(bulletText));
        }
    } else if (isCompanyLine(trimmed)) {
        // Company · Location | Date — split on last pipe
        const pipeIndex = trimmed.lastIndexOf(' | ');
        const company = trimmed.substring(0, pipeIndex).trim();
        const date = trimmed.substring(pipeIndex + 3).trim();
        children.push(new Paragraph({
            spacing: { before: 0, after: 20 },
            children: [
                new TextRun({ text: company, size: 17, color: "666666", font: FONT }),
                new TextRun({ text: "   " + date, size: 17, color: "444444", font: FONT })
            ]
        }));
    } else if (isJobTitle(trimmed)) {
        // Job title — add spacer before each except the first
        if (!isFirstJob) children.push(spacer());
        isFirstJob = false;
        children.push(new Paragraph({
            spacing: { before: 0, after: 10 },
            children: [new TextRun({
                text: trimmed,
                bold: true,
                size: 19,
                color: DARK,
                font: FONT
            })]
        }));
    } else {
        // Fallback — render as bullet
        children.push(bulletPara(trimmed));
    }
});

children.push(spacer());

// --- RECOGNITION & PROFESSIONAL COMMUNITY ---
children.push(sectionHeading("RECOGNITION & PROFESSIONAL COMMUNITY"));
if (data.tables.recognition) {
    children.push(twoColTable(data.tables.recognition));
}
children.push(spacer());

// --- EDUCATION & CERTIFICATIONS ---
if (data.tables.education) {
    children.push(sectionHeading("EDUCATION & CERTIFICATIONS"));
    children.push(twoColTable(data.tables.education));
    children.push(spacer());
}

// --- TOOLS & METHODOLOGIES ---
if (data.tables.tools) {
    children.push(sectionHeading("TOOLS & METHODOLOGIES"));
    children.push(twoColTable(data.tables.tools));
    children.push(spacer());
}

// --- LANGUAGES ---
if (data.tables.languages) {
    children.push(sectionHeading("LANGUAGES"));
    children.push(twoColTable(data.tables.languages));
}

// --- ASSEMBLE DOCUMENT ---
const doc = new Document({
    sections: [{
        properties: {
            page: {
                size: { width: 11906, height: 16838 },
                margin: { top: 1080, right: 1080, bottom: 1080, left: 1080 }
            }
        },
        children: children
    }]
});

Packer.toBuffer(doc).then(buffer => {
    const filename = `${data.filename}.docx`;
    fs.writeFileSync(filename, buffer);
    console.log(`Saved: ${filename}`);
});