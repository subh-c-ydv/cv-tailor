const { Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
        AlignmentType, WidthType, BorderStyle, ShadingType } = require('docx');
const fs = require('fs');

const data = JSON.parse(fs.readFileSync('cv_data.json', 'utf8'));
const structure = data.structure;

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

// --- Experience line parsing ---
// A job block in the data comes in one of two shapes:
//   1. A single combined line: "Title | Company · Location | Date"        (3 pipe-parts)
//   2. Two lines: a title-only line (e.g. "Earlier Career (2002 - 2014)")
//      followed by a "Company | Date" line                                (2 pipe-parts)
// Bullets always start with "•" or "-".
// We classify by pipe-part COUNT rather than by content pattern, since
// job header lines legitimately contain both "|" and a date, which made
// the old content-based classifier misfire on every normal role.

function isDateLike(line) {
    return /\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}/.test(line) ||
           /\d{4}\s*[\u2013\-]\s*(Present|\d{4})/.test(line);
}

function isPlaceholder(text) {
    const t = text.replace(/^[\u2022\-]\s*/, '').trim();
    return t === '--' || t === '' || t === '-';
}

function renderExperienceSection(lines) {
    const children = [];
    let isFirstJob = true;

    lines.forEach(line => {
        const trimmed = line.trim();
        if (!trimmed) return;
        if (isPlaceholder(trimmed)) return;

        // Bullet point
        if (trimmed.startsWith('\u2022') || trimmed.startsWith('-')) {
            const bulletText = trimmed.replace(/^[\u2022\-]\s*/, '').trim();
            if (bulletText && !isPlaceholder(bulletText)) {
                children.push(bulletPara(bulletText));
            }
            return;
        }

        if (trimmed.includes('|')) {
            const parts = trimmed.split('|').map(p => p.trim());

            if (parts.length >= 3) {
                // Full job header on one line: Title | Company | Date
                if (!isFirstJob) children.push(spacer());
                isFirstJob = false;

                const title = parts[0];
                const company = parts.slice(1, -1).join(' | ');
                const date = parts[parts.length - 1];

                children.push(new Paragraph({
                    spacing: { before: 0, after: 10 },
                    children: [new TextRun({
                        text: title,
                        bold: true,
                        size: 19,
                        color: DARK,
                        font: FONT
                    })]
                }));
                children.push(new Paragraph({
                    spacing: { before: 0, after: 20 },
                    children: [
                        new TextRun({ text: company, size: 17, color: "666666", font: FONT }),
                        new TextRun({ text: "   " + date, size: 17, color: "444444", font: FONT })
                    ]
                }));
                return;
            }

            if (parts.length === 2) {
                // Company | Date only — subtitle belonging to a title rendered
                // on the previous (no-pipe) line, e.g. the Earlier Career block
                const company = parts[0];
                const date = parts[1];
                children.push(new Paragraph({
                    spacing: { before: 0, after: 20 },
                    children: [
                        new TextRun({ text: company, size: 17, color: "666666", font: FONT }),
                        new TextRun({ text: "   " + date, size: 17, color: "444444", font: FONT })
                    ]
                }));
                return;
            }
        }

        // No pipe at all — a title-only heading line (e.g. "Earlier Career (2002 - 2014)")
        // Always starts a new job block.
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

// --- DYNAMIC SECTIONS --- render in order defined in cv_structure.txt
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
        children.push(twoColTable(data.tables[key]));
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
    const filename = `${data.filename}.docx`;
    fs.writeFileSync(filename, buffer);
    console.log(`Saved: ${filename}`);
});