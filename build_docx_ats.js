const { Document, Packer, Paragraph, TextRun, AlignmentType, BorderStyle } = require('docx');
const fs = require('fs');

const data = JSON.parse(fs.readFileSync('cv_data.json', 'utf8'));
const structure = data.structure;

const DARK = "1F2D3D";
const ACCENT = "2E75B6";
const FONT = "Calibri";

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

// ATS-friendly table renderer — plain text, no tables
function renderTableAsText(rows, heading) {
    const children = [];

    // Core Competencies — just the names as a clean list
    if (heading.toLowerCase().includes("competenc")) {
        // Extract first column (competency names) only
        const names = rows.map(row => row[0] || '').filter(n => n.trim());
        // Render as two per line separated by pipe for scannability
        for (let i = 0; i < names.length; i += 2) {
            const line = names[i + 1]
                ? `${names[i]}   |   ${names[i + 1]}`
                : names[i];
            children.push(para(line, { size: 17, spaceAfter: 40 }));
        }
        return children;
    }

    // All other table sections — label bold, description on same or next line
    rows.forEach(row => {
        if (row[0]) {
            children.push(para(row[0], { bold: true, size: 17, spaceAfter: 20 }));
        }
        if (row[1]) {
            children.push(para(row[1], { size: 17, spaceAfter: 40 }));
        }
    });

    return children;
}

function isJobHeader(line) {
    return /\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}/.test(line) ||
           /\d{4}\s*[–\-]\s*(Present|\d{4})/.test(line);
}

function isCompanyLine(line) {
    return line.includes(' | ') && isJobHeader(line);
}

function isJobTitle(line) {
    if (line.startsWith('Earlier Career') || line.startsWith('Earlier Experience')) return true;
    return !line.startsWith('•') &&
           !line.startsWith('-') &&
           !isCompanyLine(line);
}

function isPlaceholder(text) {
    const t = text.replace(/^[•\-]\s*/, '').trim();
    return t === '--' || t === '' || t === '-';
}

function parseJobHeader(line) {
    const parts = line.split('|').map(p => p.trim());
    if (parts.length === 3) return { title: parts[0], company: parts[1], date: parts[2] };
    if (parts.length === 2) return { title: parts[0], company: '', date: parts[1] };
    return null;
}

function renderExperienceSection(lines) {
    const children = [];
    let isFirstJob = true;

    lines.forEach(line => {
        const trimmed = line.trim();
        if (!trimmed) return;
        if (isPlaceholder(trimmed)) return;

        if (trimmed.startsWith('•') || trimmed.startsWith('-')) {
            const bulletText = trimmed.replace(/^[•\-]\s*/, '').trim();
            if (bulletText && !isPlaceholder(bulletText)) {
                children.push(bulletPara(bulletText));
            }
        } else if (isCompanyLine(trimmed)) {
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
            children.push(bulletPara(trimmed));
        }
    });

    return children;
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

// --- DYNAMIC SECTIONS ---
const sectionOrder = Object.keys(structure.section_map).filter(
    k => structure.section_map[k] !== 'header'
);

sectionOrder.forEach(heading => {
    const key = structure.section_map[heading];
    const isNarrative = structure.narrative_sections.includes(heading);
    const isTable = structure.table_sections.includes(heading);

    if (isNarrative) {
        children.push(sectionHeading(heading));

        if (heading.toLowerCase().includes('experience')) {
            const expLines = data.professional_experience || [];
            renderExperienceSection(expLines).forEach(c => children.push(c));
        } else {
            const text = data.professional_summary || '';
            children.push(para(text, { size: 17, spaceAfter: 80 }));
        }
        children.push(spacer());

    } else if (isTable && data.tables[key]) {
        children.push(sectionHeading(heading));
        // Render as plain text instead of table
        renderTableAsText(data.tables[key], heading).forEach(c => children.push(c));
        children.push(spacer());
    }
});

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
    const filename = `${data.filename}_ATS.docx`;
    fs.writeFileSync(filename, buffer);
    console.log(`Saved ATS version: ${filename}`);
});