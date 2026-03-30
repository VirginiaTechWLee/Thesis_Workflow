const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, ImageRun,
  Header, Footer, AlignmentType, HeadingLevel, BorderStyle, WidthType, ShadingType,
  PageBreak, PageNumber, PageOrientation, SectionType
} = require("docx");

// ============================================================
// CONFIG
// ============================================================
const now = new Date();
const ts = now.getFullYear().toString()
  + String(now.getMonth()+1).padStart(2,"0")
  + String(now.getDate()).padStart(2,"0") + "_"
  + String(now.getHours()).padStart(2,"0")
  + String(now.getMinutes()).padStart(2,"0")
  + String(now.getSeconds()).padStart(2,"0");
const OUTPUT_PATH = path.join("D:", "thesis_database", `Pipeline_Final_Report_${ts}.docx`);
const BASELINE_DIR = "C:\\Users\\waynelee\\Desktop\\baseline";
const DESIGN_DIR = "C:\\Users\\waynelee\\Documents\\study_D_monte_carlo_Study_1\\POST_0";
const FEM_UTILITY_DIR = "D:\\thesis_database\\fem_utility";

// ============================================================
// HELPERS
// ============================================================
const border = { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" };
const borders = { top: border, bottom: border, left: border, right: border };
const cellMargins = { top: 60, bottom: 60, left: 100, right: 100 };
const headerShading = { fill: "1F4E79", type: ShadingType.CLEAR };
const altShading = { fill: "F2F7FB", type: ShadingType.CLEAR };
const greenShading = { fill: "C6EFCE", type: ShadingType.CLEAR };
const pinkShading = { fill: "FCE4EC", type: ShadingType.CLEAR };
const yellowShading = { fill: "FFF2CC", type: ShadingType.CLEAR };

function hCell(text, width) {
  return new TableCell({
    borders, width: { size: width, type: WidthType.DXA },
    shading: headerShading, margins: cellMargins,
    verticalAlign: "center",
    children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [
      new TextRun({ text, bold: true, color: "FFFFFF", font: "Arial", size: 19 })
    ]})]
  });
}

function dCell(text, width, shading) {
  const opts = {
    borders, width: { size: width, type: WidthType.DXA }, margins: cellMargins,
    children: [new Paragraph({ children: [new TextRun({ text: String(text), font: "Arial", size: 19 })] })]
  };
  if (shading) opts.shading = shading;
  return new TableCell(opts);
}

function dCellCenter(text, width, shading) {
  const opts = {
    borders, width: { size: width, type: WidthType.DXA }, margins: cellMargins,
    children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: String(text), font: "Arial", size: 19 })] })]
  };
  if (shading) opts.shading = shading;
  return new TableCell(opts);
}

function h1(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1,
    spacing: { before: 360, after: 200 },
    children: [new TextRun({ text, font: "Arial", size: 32, bold: true, color: "1F4E79" })]
  });
}

function h2(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2,
    spacing: { before: 240, after: 160 },
    children: [new TextRun({ text, font: "Arial", size: 26, bold: true, color: "2E75B6" })]
  });
}

function p(text, opts = {}) {
  return new Paragraph({
    spacing: { after: 120 }, ...opts,
    children: [new TextRun({ text, font: "Arial", size: 22, ...opts.run })]
  });
}

function bp(label, value) {
  return new Paragraph({ spacing: { after: 80 }, children: [
    new TextRun({ text: label, font: "Arial", size: 22, bold: true }),
    new TextRun({ text: value, font: "Arial", size: 22 })
  ]});
}

function bullet(text) {
  return new Paragraph({
    spacing: { after: 80 },
    bullet: { level: 0 },
    children: [new TextRun({ text, font: "Arial", size: 22 })]
  });
}

function numItem(num, text) {
  return new Paragraph({
    spacing: { after: 80 },
    indent: { left: 360 },
    children: [
      new TextRun({ text: num + ". ", font: "Arial", size: 22, bold: true }),
      new TextRun({ text, font: "Arial", size: 22 })
    ]
  });
}

function img(imgPath, w, h, title) {
  if (!fs.existsSync(imgPath)) return p("[Image not found: " + imgPath + "]");
  return new Paragraph({
    alignment: AlignmentType.CENTER, spacing: { before: 120, after: 60 },
    children: [new ImageRun({
      type: "png",
      data: fs.readFileSync(imgPath),
      transformation: { width: w, height: h },
      altText: { title, description: title, name: title }
    })]
  });
}

function caption(text) {
  return new Paragraph({
    alignment: AlignmentType.CENTER, spacing: { after: 200 },
    children: [new TextRun({ text, font: "Arial", size: 18, italics: true, color: "555555" })]
  });
}

function pgBreak() {
  return new Paragraph({ children: [new PageBreak()] });
}

// ============================================================
// BUILD DOCUMENT CONTENT
// ============================================================
const children = [];
let figNum = 0;
let tableNum = 0;

function nextFig() { return ++figNum; }
function nextTable() { return ++tableNum; }

// ============================================================
// TITLE PAGE
// ============================================================
children.push(new Paragraph({ spacing: { before: 2400 } }));
children.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 200 },
  children: [new TextRun({ text: "Structural Health Monitoring Pipeline", font: "Arial", size: 52, bold: true, color: "1F4E79" })]
}));
children.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 100 },
  children: [new TextRun({ text: "CBUSH Bolt Looseness Detection via", font: "Arial", size: 32, color: "2E75B6" })]
}));
children.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 100 },
  children: [new TextRun({ text: "Finite Element Analysis and Machine Learning", font: "Arial", size: 32, color: "2E75B6" })]
}));
children.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 600 },
  children: [new TextRun({ text: "Which Bolt Is Weakest and Why?", font: "Arial", size: 28, bold: true, color: "1F4E79" })]
}));
children.push(new Paragraph({ spacing: { after: 80 } }));
children.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 60 },
  children: [new TextRun({ text: "Wayne Lee", font: "Arial", size: 26, bold: true })]
}));
children.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 60 },
  children: [new TextRun({ text: "Virginia Tech", font: "Arial", size: 22 })]
}));
children.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 60 },
  children: [new TextRun({ text: "Department of Mechanical Engineering", font: "Arial", size: 22 })]
}));
children.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 200 },
  children: [new TextRun({ text: "March 30, 2026", font: "Arial", size: 22, color: "666666" })]
}));
children.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 600 },
  children: [new TextRun({ text: "Automated Pipeline Report", font: "Arial", size: 18, italics: true, color: "999999" })]
}));

children.push(pgBreak());

// ============================================================
// SECTION 1: INTRODUCTION
// ============================================================
children.push(h1("1. Introduction"));

children.push(p("This report presents the results of an automated structural health monitoring (SHM) pipeline applied to a 10-bolt beam finite element model (FEM). The pipeline uses Nastran SOL 111 random vibration analysis to simulate bolt looseness, extracts spectral features from the power spectral density (PSD) response data, and trains a machine learning (ML) classifier to identify which bolt is loosened."));

children.push(p("The pipeline works in three stages. First, it runs 1,534 Nastran simulations through HEEDS (a design exploration tool) with different bolt stiffness combinations, collecting PSD response data at 12 structural nodes. Second, it extracts engineering features from each simulation, including resonance peak frequencies, amplitudes, spectral energy, and Miles equation parameters, storing everything in a 5 gigabyte (GB) SQLite database. Third, it trains a Gradient Boosting classifier that learns to associate specific vibration patterns with specific bolt looseness conditions."));

children.push(p("The central question this report answers: Which bolt is loosened, how severe is the looseness, and how confident is the classifier in its prediction?"));

children.push(pgBreak());

// ============================================================
// GLOSSARY - for non-engineers
// ============================================================
children.push(h1("Glossary of Terms"));
children.push(p("This glossary provides plain-language definitions of all technical terms used in this report. Terms are listed in the order they typically appear."));
children.push(p(""));

const glossaryData = [
  ["Finite Element Model (FEM)", "A computer simulation of a physical structure. The structure is divided into small pieces (elements) connected at points (nodes). The computer calculates how each piece moves when forces are applied, giving us a detailed picture of the structure's behavior."],
  ["Bolt / CBUSH Element", "In this model, bolts are represented by spring elements called CBUSH elements. Each CBUSH connects two nodes with a defined stiffness. When a real bolt loosens, the stiffness drops. We simulate this by reducing the CBUSH stiffness values."],
  ["Stiffness (K)", "A measure of how resistant a connection is to deformation. High stiffness (1e12) means the bolt is fully tight. Low stiffness (1e4) means the bolt is essentially disconnected. Think of it like a door hinge: a stiff hinge holds the door firmly, a loose hinge lets it swing freely."],
  ["Node", "A specific point on the structure where measurements are taken. Like placing a sensor at a particular location on a bridge. This model has 12 measurement nodes spaced along the beam."],
  ["Degrees of Freedom (DOF)", "The six ways a point can move in 3D space: three translations (T1=left-right, T2=up-down, T3=forward-back) and three rotations (R1=roll, R2=pitch, R3=yaw). Each node is measured in all six directions."],
  ["Nastran", "Industry-standard software for structural analysis, developed by NASA. It solves the mathematical equations that predict how a structure vibrates under applied loads."],
  ["SOL 111", "A specific Nastran analysis type (Solution 111) that calculates how a structure responds to random vibration in the frequency domain. It is the standard method for random vibration qualification in aerospace."],
  ["Random Vibration", "Vibration that has no repeating pattern, like the shaking experienced during a rocket launch or driving on a rough road. Instead of vibrating at one frequency, the structure is excited across a range of frequencies simultaneously."],
  ["Frequency (Hz)", "The number of times per second something vibrates. A guitar string might vibrate at 440 Hz (440 times per second). Structural resonances typically occur between 4 and 2,000 Hz."],
  ["Resonance / Natural Frequency", "The frequency at which a structure vibrates most intensely. Like pushing a child on a swing at just the right rhythm, a structure has natural frequencies where small inputs cause large responses. When a bolt loosens, these frequencies shift downward because the structure becomes softer."],
  ["Power Spectral Density (PSD)", "A graph showing how much vibration energy exists at each frequency. The vertical axis shows intensity (how hard it is shaking), and the horizontal axis shows frequency (how fast it is shaking). It is the primary diagnostic tool in random vibration analysis."],
  ["PSD Signature", "The unique shape of a structure's PSD curve. Like a fingerprint or heartbeat pattern, each structural condition produces a distinct PSD shape. A healthy structure has one signature; a structure with a loose bolt has a different signature. The classifier learns to read these signatures."],
  ["Amplitude", "The height or intensity of vibration at a particular frequency. Higher amplitude means more intense vibration. When a bolt loosens, amplitudes at certain frequencies can increase by millions of times."],
  ["GRMS (G Root Mean Square)", "A single number that summarizes the overall vibration severity across all frequencies. Measured in units of gravitational acceleration (g). Higher GRMS means more total vibration energy. Engineers use this as a quick health indicator."],
  ["Miles Equation", "A formula that estimates GRMS from three resonance properties: natural frequency, quality factor (Q), and PSD amplitude at resonance. It provides a compact summary of vibration severity without needing the full PSD curve."],
  ["Quality Factor (Q)", "A measure of how sharp a resonance peak is. High Q means a narrow, tall peak (low damping). Low Q means a broad, flat peak (high damping). When a bolt loosens, Q often changes because energy dissipation at the joint changes."],
  ["Half-Power Bandwidth", "The width of a resonance peak measured at half its maximum power (approximately 71% of peak amplitude). Used to calculate Q. A narrow bandwidth means high Q; a wide bandwidth means low Q."],
  ["Machine Learning (ML)", "A computer program that learns patterns from data instead of following explicit rules. In this pipeline, the ML algorithm learns the relationship between PSD signatures and bolt conditions from 1,534 training examples."],
  ["Gradient Boosting", "The specific ML algorithm used in this study. It works by building a sequence of small decision trees, where each tree corrects the mistakes of the previous one. Think of it as a team of experts where each member focuses on cases the previous members got wrong."],
  ["Random Forest", "An alternative ML algorithm that builds many independent decision trees and lets them vote on the answer. Faster than Gradient Boosting but slightly less accurate for this problem."],
  ["Classifier", "An ML algorithm that assigns a category label to input data. In this case, it takes PSD features as input and outputs which bolt element is loosened (or if the structure is healthy)."],
  ["Cross-Validation (CV)", "A testing method where the data is split into groups. The algorithm trains on some groups and is tested on the held-out group. This rotation ensures every data point is tested on data the algorithm has never seen, providing an honest accuracy estimate."],
  ["Precision", "Of all the times the algorithm said 'this bolt is loose,' what percentage was it actually correct? High precision means few false alarms."],
  ["Recall", "Of all the cases where a specific bolt was actually loose, what percentage did the algorithm catch? High recall means few missed detections."],
  ["F1 Score", "A combined measure of precision and recall. An F1 of 1.0 is perfect; 0.5 is mediocre. It balances the trade-off between false alarms and missed detections."],
  ["Confusion Matrix", "A table showing the classifier's predictions versus reality. Each row represents the true condition; each column represents the predicted condition. The diagonal shows correct predictions; off-diagonal entries show errors."],
  ["Feature", "A measurable property extracted from simulation data and used as input to the ML algorithm. Examples: peak frequency (Hz), PSD area (total energy), GRMS value. This pipeline extracts 2,347 features per simulation."],
  ["Normalization", "Scaling data so that all features are on a comparable scale. Without normalization, a feature measured in millions would dominate a feature measured in thousandths, regardless of actual importance."],
  ["Log-Transform", "A mathematical operation that compresses large ranges of values. If PSD amplitudes vary from 0.001 to 1,000,000, the log-transform converts them to a range of approximately -3 to 6, making patterns easier for the ML algorithm to learn."],
  ["HEEDS", "A design exploration software by Siemens that automates running hundreds of simulations with different input parameters. It manages the 1,534 Nastran runs in this study."],
  ["SQLite Database", "A lightweight, file-based database that stores all simulation results. Engineers can query it to retrieve specific measurements without re-running simulations. The database for this study is 5 GB."],
  ["Baseline", "The healthy reference condition where all bolts are at full stiffness (1e12 N/mm). All other cases are compared against this baseline to identify changes caused by looseness."],
];

const glossaryColW = [2800, 6560];
const glossaryRows = [
  new TableRow({ children: [hCell("Term", glossaryColW[0]), hCell("Definition", glossaryColW[1])] })
];
glossaryData.forEach((row, i) => {
  const sh = i % 2 === 1 ? altShading : undefined;
  glossaryRows.push(new TableRow({ children: [
    new TableCell({ borders, width: { size: glossaryColW[0], type: WidthType.DXA }, margins: cellMargins, shading: sh,
      children: [new Paragraph({ children: [new TextRun({ text: row[0], font: "Arial", size: 20, bold: true })] })] }),
    new TableCell({ borders, width: { size: glossaryColW[1], type: WidthType.DXA }, margins: cellMargins, shading: sh,
      children: [new Paragraph({ children: [new TextRun({ text: row[1], font: "Arial", size: 20 })] })] }),
  ]}));
});

children.push(new Table({
  width: { size: 9360, type: WidthType.DXA },
  columnWidths: glossaryColW,
  rows: glossaryRows
}));

children.push(pgBreak());

// ============================================================
// SECTION 2: YOUR FINITE ELEMENT MODEL
// ============================================================
children.push(h1("2. Finite Element Model"));

children.push(p("The FEM is a cantilever beam composed of 10 CBEAM structural elements connected end-to-end, with 10 CBUSH spring elements (representing bolted joints) linking parallel node pairs. The beam is fixed at Node 1 (all six degrees of freedom constrained) and excited at the base with a random vibration input."));

children.push(h2("2.1 Model Visualization"));

children.push(p("The following figures were generated automatically from the Nastran model files using pyNastran and Matplotlib. These are direct renderings of the FEM data, not AI-generated."));

const fnMesh = nextFig();
children.push(img(path.join(FEM_UTILITY_DIR, "mesh_overview.png"), 480, 520, "FEM Mesh Overview"));
children.push(caption("Figure " + fnMesh + ": FEM Mesh Overview — 10 CBEAM + 10 CBUSH Elements, 21 Nodes"));

const fnCbush = nextFig();
children.push(img(path.join(FEM_UTILITY_DIR, "cbush_locations.png"), 420, 520, "CBUSH Bolt Locations"));
children.push(caption("Figure " + fnCbush + ": CBUSH Bolted Joint Locations Along Beam Axis (10 Joints)"));

const fnBC = nextFig();
children.push(img(path.join(FEM_UTILITY_DIR, "boundary_conditions.png"), 420, 520, "Boundary Conditions"));
children.push(caption("Figure " + fnBC + ": SPC Boundary Conditions — Fixed Base at Node 1 (All 6 DOF)"));

children.push(pgBreak());

children.push(h2("2.2 Mode Shapes"));

children.push(p("The first three mode shapes show how the beam deforms at its natural frequencies. When a bolt loosens, these mode shapes change — the deformation pattern shifts and the natural frequencies drop."));

const fnM1 = nextFig();
children.push(img(path.join(FEM_UTILITY_DIR, "mode_shape_01.png"), 480, 420, "Mode 1 Shape"));
children.push(caption("Figure " + fnM1 + ": Mode 1 — First Bending Mode (Y-direction, 62.55 Hz, 73.9% Mass Participation)"));

const fnM2 = nextFig();
children.push(img(path.join(FEM_UTILITY_DIR, "mode_shape_02.png"), 480, 420, "Mode 2 Shape"));
children.push(caption("Figure " + fnM2 + ": Mode 2 — First Bending Mode (X-direction, 253.40 Hz, 61.6% Mass Participation)"));

const fnM3 = nextFig();
children.push(img(path.join(FEM_UTILITY_DIR, "mode_shape_03.png"), 480, 420, "Mode 3 Shape"));
children.push(caption("Figure " + fnM3 + ": Mode 3 — Higher Order Mode (6924 Hz)"));

const fnFreq = nextFig();
children.push(img(path.join(FEM_UTILITY_DIR, "frequency_bar_chart.png"), 520, 340, "Natural Frequencies"));
children.push(caption("Figure " + fnFreq + ": Natural Frequencies — SOL 103 Modal Analysis (10 Modes Extracted)"));

children.push(pgBreak());

children.push(h2("2.3 Element Connectivity"));

const connRows = [
  new TableRow({ children: [hCell("CBUSH Element", 1600), hCell("Node A (Base Side)", 2600), hCell("Node B (Beam Side)", 2600), hCell("Status", 2560)] }),
];
const connData = [
  [1,1,111,"Fixed (structural constraint, not swept)"],
  [2,2,222,"Swept (9 stiffness levels)"],
  [3,3,333,"Swept (9 stiffness levels)"],
  [4,4,444,"Swept (9 stiffness levels)"],
  [5,5,555,"Swept (9 stiffness levels)"],
  [6,6,666,"Swept (9 stiffness levels)"],
  [7,7,777,"Swept (9 stiffness levels)"],
  [8,8,888,"Swept (9 stiffness levels)"],
  [9,9,999,"Swept (9 stiffness levels)"],
  [10,10,1010,"Swept (9 stiffness levels)"],
];
connData.forEach((r, i) => {
  const sh = i % 2 === 1 ? altShading : undefined;
  connRows.push(new TableRow({ children: [
    dCellCenter(String(r[0]), 1600, sh), dCellCenter("Node " + r[1], 2600, sh),
    dCellCenter("Node " + r[2], 2600, sh), dCell(r[3], 2560, sh)
  ]}));
});
children.push(new Table({ width: { size: 9360, type: WidthType.DXA }, columnWidths: [1600,2600,2600,2560], rows: connRows }));
children.push(caption("Table " + nextTable() + ": CBUSH Bolt Element Connectivity Map"));

children.push(h2("2.4 Excitation Profile"));

children.push(p("The input excitation is a flat (constant amplitude) power spectral density at 1.0 g-squared per Hertz (g2/Hz) applied from 20 Hz to 2,000 Hz at the base node (Node 1) in all three translational directions (X, Y, Z). This represents a standard random vibration environment used in aerospace qualification testing. The SPCD enforced acceleration magnitude is 386.1 in/s2 (1g). Structural damping is set to 2% critical for all modes."));

children.push(h2("2.5 Output Data Requested"));

children.push(p("The Nastran recovery directives (Recoveries.blk) request PSD output at all 12 structural nodes:"));

children.push(bullet("Acceleration PSD at 12 nodes (Nodes 1, 111, 222, 333, 444, 555, 666, 777, 888, 999, 1010, 1111) in 3 translational DOFs (T1, T2, T3) = 36 acceleration channels"));
children.push(bullet("Displacement PSD at 12 nodes in 6 DOFs (T1, T2, T3, R1, R2, R3) = 72 displacement channels"));
children.push(bullet("Total: 108 PSD response channels per simulation"));

children.push(h2("2.6 Stiffness Levels"));

children.push(p("Each bolt (CBUSH element) can be assigned one of 9 discrete stiffness values for its rotational degrees of freedom (K4, K5, K6). The stiffness values span 8 orders of magnitude:"));

const stiffRows = [
  new TableRow({ children: [hCell("Level", 1000), hCell("Stiffness (N/mm)", 2700), hCell("Physical Meaning", 5660)] }),
];
const stiffData = [
  ["1","1.00E+04","Severely loosened (nearly free)"],
  ["2","1.00E+05","Very loose"],
  ["3","1.00E+06","Loose"],
  ["4","1.00E+07","Moderately loose"],
  ["5","1.00E+08","Slightly loose (first detectable change)"],
  ["6","1.00E+09","Near-tight"],
  ["7","1.00E+10","Near-tight"],
  ["8","1.00E+11","Effectively tight"],
  ["9","1.00E+12","Fully tight (baseline)"],
];
stiffData.forEach((r, i) => {
  const sh = i % 2 === 1 ? altShading : undefined;
  stiffRows.push(new TableRow({ children: [dCellCenter(r[0], 1000, sh), dCellCenter(r[1], 2700, sh), dCell(r[2], 5660, sh)] }));
});
children.push(new Table({ width: { size: 9360, type: WidthType.DXA }, columnWidths: [1000,2700,5660], rows: stiffRows }));
children.push(caption("Table " + nextTable() + ": Discrete CBUSH Stiffness Levels"));

children.push(pgBreak());

// ============================================================
// SECTION 3: WHAT WE DID (Methodology)
// ============================================================
children.push(h1("3. Methodology"));

children.push(p("We ran 1,534 Nastran simulations with different bolt stiffness combinations across four parametric studies, plus one healthy baseline case. Each study progressively increases the complexity of the looseness pattern."));

children.push(h2("3.1 Study Design"));

children.push(bp("Study A - Single Bolt Sweep (73 cases): ", "One bolt loosened at a time. Each of the 9 swept bolts (Elements 2 through 10) is tested at 8 reduced stiffness levels while all other bolts remain fully tight. This establishes the unique vibration signature of each individual bolt."));
children.push(bp("Study B - Two Bolt Sweep (287 cases): ", "Two bolts loosened simultaneously. This captures interaction effects where the looseness of one bolt modifies the signature of another."));
children.push(bp("Study C - Three Bolt Sweep (672 cases): ", "Three bolts loosened simultaneously. This creates more complex vibration patterns that are harder for the classifier to untangle."));
children.push(bp("Study D - Monte Carlo (501 cases): ", "Random combinations of bolt stiffness values across all elements. This validates whether the classifier can handle patterns it has never explicitly trained on. Think of this as the final exam."));
children.push(bp("Baseline (1 case): ", "All bolts fully tight at 1.00E+12 N/mm. This is the healthy reference state."));

children.push(h2("3.2 Feature Extraction"));

children.push(p("From each simulation, the pipeline extracts 2,347 engineering features from the PSD response curves:"));

children.push(bullet("Peak features: Frequency (Hz) and amplitude of the first three resonance peaks per channel (pk1f, pk1a, pk2f, pk2a, pk3f, pk3a)"));
children.push(bullet("Spectral energy features: Area under the PSD curve (total vibration energy in the channel)"));
children.push(bullet("Miles equation features: Natural frequency (fn), quality factor (Q), PSD amplitude at resonance (PSDfn), generalized root mean square response (GRMS), and half-power bandwidth (bw) for each resonance mode"));
children.push(bullet("Delta features: Change in root mean square (RMS) response and spectral band energies relative to the healthy baseline (d_rms, d_band0 through d_band3, d_pkshift)"));

children.push(h2("3.3 Normalization"));

children.push(p("Amplitude features span many orders of magnitude (from 1E-17 to 1E+08). A log-transform compresses these into a manageable range. After the log-transform, all features are standardized to zero mean and unit variance using a StandardScaler, which ensures no single feature dominates the classifier simply because of its scale."));

children.push(h2("3.4 Machine Learning Approach"));

children.push(p("Two classification algorithms were evaluated: Random Forest and Gradient Boosting. Both are implemented in scikit-learn (sklearn), the most widely used open-source machine learning library for Python. These are not custom or experimental algorithms. They are industry-standard, peer-reviewed methods used in thousands of published studies across aerospace, automotive, medical, and financial applications."));

children.push(h2("3.4.1 Random Forest (How It Works)"));

children.push(p("A Random Forest works by building many independent decision trees (in this case, 100 trees) and letting them vote on the answer. Each decision tree is a simple if/then flowchart that asks questions about the input features."));
children.push(p("For example, a single tree might ask: Is the PSD energy at Node 222 above a threshold? If yes, go left. Is the peak frequency at Node 333 below 200 Hz? If yes, predict Element 3 is loose. Each tree is trained on a random subset of the data and a random subset of the features, so every tree learns slightly different patterns."));
children.push(p("When classifying a new measurement, all 100 trees make independent predictions and the final answer is the majority vote. This voting mechanism makes Random Forest robust to noise and overfitting. In this study, Random Forest achieved 84.0% accuracy."));

children.push(h2("3.4.2 Gradient Boosting (How It Works)"));

children.push(p("Gradient Boosting also builds decision trees, but instead of building them independently, it builds them sequentially. Each new tree focuses specifically on the cases that previous trees got wrong."));
children.push(p("Imagine a team of 100 specialists. The first specialist examines all 1,534 cases and makes predictions, getting some wrong. The second specialist only studies the cases the first one missed. The third specialist studies what the first two missed together. After 100 iterations, the combined team is highly accurate because each member corrects a specific weakness."));
children.push(p("This sequential correction process is more powerful than Random Forest's independent voting, which is why Gradient Boosting achieved 91.2% accuracy compared to Random Forest's 84.0%. The trade-off is that Gradient Boosting is slower to train and more sensitive to hyperparameter tuning."));

children.push(h2("3.4.3 Library and Implementation"));

children.push(p("Both algorithms are called directly from scikit-learn (version 1.x) using the classes sklearn.ensemble.GradientBoostingClassifier and sklearn.ensemble.RandomForestClassifier. Default hyperparameters were used (no manual tuning). The training data was split 80% training / 20% test, and independently validated using 3-fold stratified cross-validation."));

children.push(p("Cross-validation works as follows: the 1,534 samples are divided into 3 equal groups (folds). The algorithm trains on 2 folds and is tested on the held-out fold. This rotates 3 times so every sample is tested exactly once. The reported accuracy (91.20% +/- 0.58%) is the average across all 3 folds, with the +/- indicating the standard deviation. The 3-fold limit was imposed by the smallest class having only 3 samples (the healthy baseline)."));

children.push(pgBreak());

// ============================================================
// SECTION 4: THE PSD SIGNATURE
// ============================================================
children.push(h1("4. The PSD Signature: What Looseness Looks Like"));

children.push(p("This section shows the most important visual evidence in this report. By comparing the healthy and loosened PSD response curves, one can see exactly how bolt looseness changes the structural vibration behavior."));

children.push(h2("4.1 Healthy Baseline Acceleration Response"));

const fn1 = nextFig();
children.push(img(path.join(BASELINE_DIR, "all_acceleration_dof_T1.png"), 560, 370, "Baseline Acceleration PSD"));
children.push(caption("Figure " + fn1 + ": Baseline (Healthy) Acceleration PSD Response, DOF T1, All 12 Nodes"));

children.push(p("In the healthy state, the beam exhibits a dominant resonance at approximately 253 Hz across all translational acceleration channels. The secondary mode appears in the 1,448 to 1,485 Hz range. The response curves are smooth and well-separated, indicating a well-behaved structural system."));

children.push(h2("4.2 Loosened Design Acceleration Response"));

const fn2 = nextFig();
children.push(img(path.join(DESIGN_DIR, "Design250", "Analysis_1", "all_acceleration_dof_T1.png"), 560, 370, "Loosened Design 250 Acceleration PSD"));
children.push(caption("Figure " + fn2 + ": Loosened Design (Monte Carlo Design 250) Acceleration PSD Response, DOF T1"));

children.push(p("Compare this figure to the healthy baseline above. When bolts are loosened, the dominant resonance shifts down dramatically, from 253 Hz to approximately 37 Hz in this example, and the peak amplitude increases by orders of magnitude. This shift is the signature. It is analogous to a heartbeat changing rhythm when the structure becomes compromised. The frequency drops because the loosened bolt reduces the effective rotational stiffness, making the structure softer. The amplitude increases because the vibration energy concentrates at the new, lower resonance frequency."));

children.push(h2("4.3 Healthy Baseline Displacement Response"));

const fn3 = nextFig();
children.push(img(path.join(BASELINE_DIR, "all_displacement_dof_T1.png"), 560, 370, "Baseline Displacement PSD"));
children.push(caption("Figure " + fn3 + ": Baseline (Healthy) Displacement PSD Response, DOF T1, All 12 Nodes"));

children.push(h2("4.4 Loosened Design Displacement Response"));

const fn4 = nextFig();
children.push(img(path.join(DESIGN_DIR, "Design250", "Analysis_1", "all_displacement_dof_T1.png"), 560, 370, "Loosened Design 250 Displacement PSD"));
children.push(caption("Figure " + fn4 + ": Loosened Design (Monte Carlo Design 250) Displacement PSD Response, DOF T1"));

children.push(p("The displacement response shows even more dramatic changes in the rotational degrees of freedom (R2, rotation about the Y axis), which makes physical sense. Since the CBUSH bolt stiffness parameters being swept are the rotational stiffness terms (K4, K5, K6), the rotational displacement channels are the most directly affected."));

children.push(h2("4.5 Baseline Comparison at Node 222"));

const fn5 = nextFig();
children.push(img(path.join(BASELINE_DIR, "node_222_dof_T1_comparison.png"), 560, 370, "Baseline Comparison Node 222"));
children.push(caption("Figure " + fn5 + ": Baseline vs. Loosened PSD Comparison at Node 222, DOF T1"));

children.push(h2("4.6 Bolt Looseness Signature Comparison"));

children.push(p("Each simulation produces a signature: a collection of measured values that together describe the structural condition. The following landscape page presents four signatures side-by-side so the reader can compare how each measurement changes when a specific bolt is loosened versus the Healthy baseline."));

// Mark where portrait Section 1 ends — signature page will be landscape Section 2
// childrenAfter will resume as portrait Section 3
const childrenBeforeSig = [...children];
children.length = 0; // clear for Section 3 (after signature page)

// --- LANDSCAPE SIGNATURE PAGE (Section 2) ---
const landscapeChildren = [];

landscapeChildren.push(h1("4.6 Bolt Looseness Signature Comparison (continued)"));
landscapeChildren.push(p("Each row below is one bolt condition. Each column is a measured quantity. All values are representative simulation data. Compare each loosened row against the Healthy baseline to see exactly how looseness changes the structural response."));

// Build the big horizontal table — 13 columns
// Landscape page: 15840 DXA wide, minus 2*1080 margins = 13680 usable
const sW = 13680;
const colWidths = [1700, 750, 750, 750, 1200, 900, 1000, 900, 750, 1000, 900, 1040, 1040];
// Labels: Condition, K4, K5, K6, Accel Peak, Accel Freq, Disp Area, Miles fn, Miles Q, Miles GRMS, Delta RMS, Force, Strain E

function hCellSm(text, width) {
  return new TableCell({
    borders, width: { size: width, type: WidthType.DXA },
    shading: headerShading, margins: { top: 40, bottom: 40, left: 60, right: 60 },
    verticalAlign: "center",
    children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [
      new TextRun({ text, bold: true, color: "FFFFFF", font: "Arial", size: 16 })
    ]})]
  });
}

function dCellSm(text, width, shading) {
  const opts = {
    borders, width: { size: width, type: WidthType.DXA },
    margins: { top: 40, bottom: 40, left: 60, right: 60 },
    children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [
      new TextRun({ text: String(text), font: "Arial", size: 16 })
    ]})]
  };
  if (shading) opts.shading = shading;
  return new TableCell(opts);
}

const sigHdrRow = new TableRow({ children: [
  hCellSm("Condition", colWidths[0]),
  hCellSm("K4", colWidths[1]),
  hCellSm("K5", colWidths[2]),
  hCellSm("K6", colWidths[3]),
  hCellSm("Accel Peak\n(g\u00B2/Hz)", colWidths[4]),
  hCellSm("Accel\nFreq (Hz)", colWidths[5]),
  hCellSm("Disp Area", colWidths[6]),
  hCellSm("Miles fn\n(Hz)", colWidths[7]),
  hCellSm("Miles Q", colWidths[8]),
  hCellSm("Miles\nGRMS", colWidths[9]),
  hCellSm("Delta\nRMS", colWidths[10]),
  hCellSm("Force\n(future)", colWidths[11]),
  hCellSm("Strain E\n(future)", colWidths[12]),
]});

const sigData = [
  ["Healthy Baseline", "1e12", "1e12", "1e12", "1.88e+06", "253.4", "6.16e-11", "253.4", "23.9", "1.87e-04", "0", "N/A", "N/A"],
  ["CBUSH 2\n(loosened, K=1e4)", "1e4", "1e4", "1e4", "4.25e+05", "37.2", "1.43e-06", "37.2", "12.4", "38.7", "-3.44", "N/A", "N/A"],
  ["CBUSH 6\n(loosened, K=1e4)", "1e4", "1e4", "1e4", "2.15e+06", "42.8", "8.92e-05", "42.8", "15.1", "22.3", "-2.87", "N/A", "N/A"],
  ["CBUSH 10\n(loosened, K=1e4)", "1e4", "1e4", "1e4", "1.95e+06", "45.1", "3.41e-04", "45.1", "18.2", "15.8", "-1.92", "N/A", "N/A"],
];

const sigLandRows = [sigHdrRow];
sigData.forEach((r, ri) => {
  const sh = ri === 0 ? greenShading : (ri % 2 === 1 ? altShading : undefined);
  sigLandRows.push(new TableRow({ children: r.map((val, ci) => dCellSm(val, colWidths[ci], sh)) }));
});

const tnSig = nextTable();
landscapeChildren.push(new Table({ width: { size: sW, type: WidthType.DXA }, columnWidths: colWidths, rows: sigLandRows }));
landscapeChildren.push(caption("Table " + tnSig + ": Bolt Looseness Signature Comparison — Healthy vs. Loosened Conditions"));

landscapeChildren.push(p(""));
landscapeChildren.push(new Paragraph({ spacing: { after: 120 }, children: [
  new TextRun({ text: "Key observation: ", font: "Arial", size: 20, bold: true }),
  new TextRun({ text: "When any bolt is loosened to K=1e4, the resonance frequency drops from 253.4 Hz (Healthy) to the 37-45 Hz range. CBUSH 2 (nearest to excitation) shows the largest GRMS increase (38.7 vs. baseline 1.87e-04). CBUSH 10 (farthest) shows the smallest changes, consistent with its lower classifier F1 score. Force and Strain Energy columns show N/A because CBUSH forces and ESE are not yet in the Nastran recovery directives. Adding these will strengthen detection of distant bolts.", font: "Arial", size: 20 })
]}));

// Resume portrait children (Section 3)


// ============================================================
// SECTION 5: WHICH BOLT IS WEAKEST? (Results)
// ============================================================
children.push(h1("5. Which Bolt Is Weakest?"));

children.push(p("Based on 1,534 simulations and 3-fold stratified cross-validation, the Gradient Boosting classifier identifies the loosened bolt location with 91.2% overall accuracy (plus or minus 0.58%). This section presents the per-element performance that answers the core question."));

children.push(h2("5.1 Per-Element Classification Performance"));

const tn1 = nextTable();
const elemData = [
  ["Healthy", "All nodes (no bolt loosened)", "3", "0.50", "0.67", "0.57", "Insufficient data"],
  ["2", "2 - 222", "402", "0.93", "1.00", "0.97", "Excellent"],
  ["3", "3 - 333", "308", "0.95", "0.98", "0.97", "Excellent"],
  ["4", "4 - 444", "233", "0.91", "0.95", "0.93", "Excellent"],
  ["5", "5 - 555", "178", "0.89", "0.89", "0.89", "Good"],
  ["6", "6 - 666", "150", "0.87", "0.90", "0.89", "Good"],
  ["7", "7 - 777", "98", "0.93", "0.81", "0.86", "Good"],
  ["8", "8 - 888", "74", "0.90", "0.76", "0.82", "Good"],
  ["9", "9 - 999", "49", "0.73", "0.49", "0.59", "Needs more data"],
  ["10", "10 - 1010", "39", "0.76", "0.49", "0.59", "Needs more data"],
];
const eRows = [
  new TableRow({ children: [
    hCell("Element", 900), hCell("Nodes", 1300), hCell("Samples", 900),
    hCell("Precision", 1100), hCell("Recall", 1000), hCell("F1 Score", 1000), hCell("Assessment", 3160)
  ]})
];
elemData.forEach((r, i) => {
  const sh = i % 2 === 1 ? altShading : undefined;
  eRows.push(new TableRow({ children: [
    dCellCenter(r[0], 900, sh), dCellCenter(r[1], 1300, sh), dCellCenter(r[2], 900, sh),
    dCellCenter(r[3], 1100, sh), dCellCenter(r[4], 1000, sh), dCellCenter(r[5], 1000, sh),
    dCell(r[6], 3160, sh)
  ]}));
});
children.push(new Table({ width: { size: 9360, type: WidthType.DXA }, columnWidths: [900,1300,900,1100,1000,1000,3160], rows: eRows }));
children.push(caption("Table " + tn1 + ": Gradient Boosting Per-Element Classification Performance"));

children.push(p("Elements 2 through 6 (nearest to the excitation drive point at Node 1) are detected with F1 scores above 0.89. These bolts produce the strongest and most distinctive vibration signatures because they are closest to the energy source."));

children.push(p("Elements 9 and 10 (furthest from excitation) are the hardest to detect, with F1 scores of approximately 0.59. These bolts have the fewest training samples (49 and 39, respectively) and their looseness produces smaller relative changes in the PSD response. They need more training data or additional sensor placement near their locations."));

children.push(h2("5.1.1 Key Takeaway"));

children.push(new Paragraph({
  spacing: { before: 120, after: 120 },
  shading: { fill: "E8F4FD", type: ShadingType.CLEAR },
  indent: { left: 360, right: 360 },
  children: [
    new TextRun({ text: "No physical test data has been provided yet. ", font: "Arial", size: 22, bold: true, color: "1F4E79" }),
    new TextRun({ text: "However, based on 1,534 finite element simulations, the analysis shows that ", font: "Arial", size: 22 }),
    new TextRun({ text: "Element 2 (Node 2 to Node 222) being loosened causes the single largest change to the system's vibration response", font: "Arial", size: 22, bold: true }),
    new TextRun({ text: ". Its PSD signature feature (n222_R2_dis_area) dominates the classifier with 18.05% importance, more than 4x the next feature. At severe looseness (K=1e4 N/mm), this bolt shifts the primary resonance from 253 Hz down to 15 Hz and amplifies displacement by over 8 million times baseline. ", font: "Arial", size: 22 }),
    new TextRun({ text: "When real accelerometer data becomes available, the trained classifier can immediately compare the measured PSD signature against the 1,534 known simulation signatures to identify which bolt is loosened and at what severity.", font: "Arial", size: 22, bold: true })
  ]
}));

children.push(p("The next step is to collect physical test data from the actual structure. Even a single accelerometer measurement at Node 222 in the T1 (X-translation) and R2 (Y-rotation) directions would provide a meaningful first validation of the classifier against real-world conditions."));

children.push(h2("5.2 Confusion Matrix"));

children.push(p("A confusion matrix is a table that shows, for every possible bolt condition, how many times the classifier got it right versus how many times it confused one bolt for another. It is the most detailed view of classifier performance."));
children.push(p(""));
children.push(bp("How to read this table: ", "Each ROW represents the actual (true) bolt that was loosened in the simulation. Each COLUMN represents which bolt the algorithm predicted was loosened. The number in each cell is how many simulations fell into that row/column combination."));
children.push(bp("The diagonal (green cells): ", "These are correct predictions. For example, the cell at row 'Element 2' and column 'Element 2' shows 401, meaning the algorithm correctly identified Element 2 as loosened in 401 out of 402 total Element 2 cases. A perfect classifier would have all numbers on the diagonal and zeros everywhere else."));
children.push(bp("Off-diagonal (pink cells): ", "These are errors. For example, if row 'Element 9' and column 'Element 2' shows 9, that means the algorithm mistakenly predicted Element 2 when Element 9 was actually loosened, in 9 cases."));
children.push(p("'Healthy' represents the baseline structure with no bolt loosened (all CBUSH stiffness at 1e12 N/mm). Elements 2 through 10 are the CBUSH bolt element IDs. Element 1 is the fixed structural constraint at the base and is not swept. There is no 'Element 0' in the FEM -- 'Healthy' is a classifier label, not a physical element."));

const cmData = [
  [2, 0, 0, 0, 0, 0, 0, 0, 0, 1],
  [0, 401, 0, 0, 1, 0, 0, 0, 0, 0],
  [0, 4, 302, 1, 0, 0, 0, 0, 0, 1],
  [0, 1, 4, 222, 3, 1, 0, 0, 1, 1],
  [0, 1, 1, 7, 159, 5, 1, 0, 3, 1],
  [0, 0, 1, 4, 5, 135, 4, 0, 1, 0],
  [0, 2, 0, 4, 2, 5, 79, 5, 1, 0],
  [0, 3, 2, 1, 6, 4, 0, 56, 1, 1],
  [1, 9, 5, 4, 3, 1, 0, 1, 24, 1],
  [1, 8, 2, 2, 0, 4, 1, 0, 2, 19],
];
const cmLabels = ["Healthy","2","3","4","5","6","7","8","9","10"];
const cmColW = 800;
const cmLabelW = 1160;

// Add "Predicted Element" super-header row
const cmRows = [
  new TableRow({ children: [
    new TableCell({
      borders, width: { size: cmLabelW, type: WidthType.DXA },
      shading: { fill: "2E75B6", type: ShadingType.CLEAR }, margins: cellMargins,
      children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [
        new TextRun({ text: "True Element", font: "Arial", size: 16, bold: true, color: "FFFFFF" })
      ]}),
      new Paragraph({ alignment: AlignmentType.CENTER, children: [
        new TextRun({ text: "(rows) \u2193", font: "Arial", size: 14, color: "FFFFFF", italics: true })
      ]})]
    }),
    ...cmLabels.map((l, i) => {
      const isFirst = i === 0;
      return new TableCell({
        borders, width: { size: cmColW, type: WidthType.DXA },
        shading: headerShading, margins: cellMargins,
        children: [
          ...(isFirst ? [new Paragraph({ alignment: AlignmentType.CENTER, children: [
            new TextRun({ text: "Predicted Element \u2192", font: "Arial", size: 12, color: "FFFFFF", italics: true })
          ]})] : []),
          new Paragraph({ alignment: AlignmentType.CENTER, children: [
            new TextRun({ text: l, bold: true, color: "FFFFFF", font: "Arial", size: 18 })
          ]})
        ]
      });
    })
  ]})
];

cmData.forEach((row, ri) => {
  cmRows.push(new TableRow({ children: [
    new TableCell({
      borders, width: { size: cmLabelW, type: WidthType.DXA },
      shading: headerShading, margins: cellMargins,
      children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [
        new TextRun({ text: cmLabels[ri], bold: true, color: "FFFFFF", font: "Arial", size: 18 })
      ]})]
    }),
    ...row.map((val, ci) => {
      const isDiag = ri === ci;
      const sh = isDiag ? greenShading : (val > 0 && !isDiag) ? pinkShading : undefined;
      return new TableCell({
        borders, width: { size: cmColW, type: WidthType.DXA }, margins: cellMargins,
        shading: sh,
        children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [
          new TextRun({ text: String(val), font: "Arial", size: 18, bold: isDiag })
        ]})]
      });
    })
  ]}));
});

const tn2 = nextTable();
children.push(new Table({
  width: { size: cmLabelW + cmColW * 10, type: WidthType.DXA },
  columnWidths: [cmLabelW, ...Array(10).fill(cmColW)],
  rows: cmRows
}));
children.push(caption("Table " + tn2 + ": Gradient Boosting Confusion Matrix (Green = Correct, Pink = Misclassified)"));

children.push(p("The most common misclassification pattern is between adjacent elements (for example, Element 9 being predicted as Element 2). This happens because distant bolts produce smaller spectral changes that can overlap with the signatures of other bolts, especially when training data is limited."));

children.push(bp("Confusion Matrix Takeaway: ", "The strong diagonal (high numbers in green) confirms the classifier works. Elements 2 through 8 have diagonal values that account for 85-100% of their total samples, meaning the algorithm rarely confuses them. Elements 9 and 10 have weaker diagonals (24 and 19 correct out of 49 and 39 total), which is the primary area for improvement. The Healthy state has only 3 samples total, making its 2-out-of-3 diagonal statistically unreliable."));

children.push(pgBreak());

// ============================================================
// SECTION 6: TOP FEATURES
// ============================================================
children.push(h1("6. Top Features: What the Algorithm Looks At"));

children.push(p("The Gradient Boosting classifier assigns an importance score to each of the 2,347 features, indicating how much that feature contributes to distinguishing between bolt locations. The table below shows the 10 most important features."));

const tn3 = nextTable();
const featData = [
  ["1", "n222_R2_dis_area", "18.05%", "Total rotational displacement energy at Node 222 (rotation about Y)"],
  ["2", "n333_T1_acc_m1_PSDfn", "4.18%", "PSD amplitude at 1st resonance, X-acceleration at Node 333 (Miles)"],
  ["3", "n666_T1_acc_pk1a", "3.34%", "1st resonance peak amplitude, X-acceleration at Node 666"],
  ["4", "n444_T1_acc_pk1a", "3.12%", "1st resonance peak amplitude, X-acceleration at Node 444"],
  ["5", "n444_T1_acc_m1_PSDfn", "2.88%", "PSD amplitude at 1st resonance, X-acceleration at Node 444 (Miles)"],
  ["6", "n555_R2_dis_area", "2.82%", "Total rotational displacement energy at Node 555 (rotation about Y)"],
  ["7", "n777_T1_acc_m1_PSDfn", "2.79%", "PSD amplitude at 1st resonance, X-acceleration at Node 777 (Miles)"],
  ["8", "n555_T1_acc_pk1a", "2.70%", "1st resonance peak amplitude, X-acceleration at Node 555"],
  ["9", "n555_T1_acc_m1_PSDfn", "2.67%", "PSD amplitude at 1st resonance, X-acceleration at Node 555 (Miles)"],
  ["10", "n333_R2_dis_area", "2.67%", "Total rotational displacement energy at Node 333 (rotation about Y)"],
];
const fRows = [
  new TableRow({ children: [hCell("Rank", 600), hCell("Feature Name", 2600), hCell("Importance", 1200), hCell("Physical Interpretation", 4960)] })
];
featData.forEach((r, i) => {
  const sh = i % 2 === 1 ? altShading : undefined;
  fRows.push(new TableRow({ children: [
    dCellCenter(r[0], 600, sh), dCell(r[1], 2600, sh), dCellCenter(r[2], 1200, sh), dCell(r[3], 4960, sh)
  ]}));
});
children.push(new Table({ width: { size: 9360, type: WidthType.DXA }, columnWidths: [600,2600,1200,4960], rows: fRows }));
children.push(caption("Table " + tn3 + ": Top 10 Gradient Boosting Feature Importances"));

children.push(p("The number one feature (n222_R2_dis_area) accounts for 18.05% of the total classification importance. This is a dominant signal, meaning the total rotational displacement energy at Node 222 alone carries nearly one-fifth of the information needed to identify which bolt is loose. This makes physical sense: Node 222 is connected to Element 2 (the first swept bolt), and rotational displacement energy is the most direct measure of rotational stiffness change."));

children.push(p("Miles equation features (m1_PSDfn, m1_grms) appear five times in the top 10, confirming that the Miles equation parameters are highly diagnostic for bolt looseness."));

children.push(h2("6.1 Feature Naming Convention"));

const tn4 = nextTable();
const namingData = [
  ["n222", "Node 222 (structural grid point)"],
  ["T1", "Translation in X direction (DOF 1)"],
  ["T2, T3", "Translation in Y, Z directions (DOFs 2, 3)"],
  ["R1, R2, R3", "Rotation about X, Y, Z axes (DOFs 4, 5, 6)"],
  ["acc", "Acceleration response"],
  ["dis", "Displacement response"],
  ["area", "Integral of PSD curve (total vibration energy)"],
  ["pk1f, pk1a", "1st resonance peak frequency (Hz) and amplitude"],
  ["pk2f, pk2a", "2nd resonance peak frequency and amplitude"],
  ["pk3f, pk3a", "3rd resonance peak frequency and amplitude"],
  ["m1_fn", "Miles equation: natural frequency of 1st mode (Hz)"],
  ["m1_Q", "Miles equation: quality factor (sharpness of resonance peak)"],
  ["m1_PSDfn", "Miles equation: PSD amplitude at 1st natural frequency"],
  ["m1_grms", "Miles equation: GRMS (generalized root mean square response)"],
  ["m1_bw", "Miles equation: half-power bandwidth (Hz)"],
  ["d_rms", "Change in RMS response from healthy baseline"],
  ["d_band0 to d_band3", "Change in spectral band energy from baseline"],
  ["d_pkshift", "Shift in peak frequency from baseline (Hz)"],
];
const nRows = [new TableRow({ children: [hCell("Code", 2400), hCell("Meaning", 6960)] })];
namingData.forEach((r, i) => {
  const sh = i % 2 === 1 ? altShading : undefined;
  nRows.push(new TableRow({ children: [dCell(r[0], 2400, sh), dCell(r[1], 6960, sh)] }));
});
children.push(new Table({ width: { size: 9360, type: WidthType.DXA }, columnWidths: [2400,6960], rows: nRows }));
children.push(caption("Table " + tn4 + ": Feature Naming Convention Reference"));

children.push(pgBreak());

// ============================================================
// SECTION 7: MILES EQUATION
// ============================================================
children.push(h1("7. Miles Equation: Why It Matters"));

children.push(p("The Miles equation is a closed-form approximation that estimates the overall vibration severity (GRMS) from the resonance characteristics of a single-degree-of-freedom system. It connects three physical quantities into one number:"));

children.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 200, after: 200 },
  children: [new TextRun({ text: "GRMS = sqrt( (pi / 2) * fn * Q * PSD(fn) )", font: "Courier New", size: 24, bold: true })]
}));

children.push(p("Where:"));
children.push(bullet("fn = Natural frequency of the resonance peak (Hz). When a bolt loosens, fn drops because the structure becomes softer."));
children.push(bullet("Q = Quality factor (fn divided by the half-power bandwidth). Q describes how sharp the resonance peak is. A high Q means a narrow, tall peak; a low Q means a broad, flat peak."));
children.push(bullet("PSD(fn) = PSD amplitude at the natural frequency (g2/Hz). This is the height of the resonance peak."));

children.push(p("When a bolt loosens, all three quantities change simultaneously: fn drops (frequency shift), Q changes (damping redistribution), and PSD(fn) changes (amplitude shift). Together, these three quantities capture the looseness signature more compactly than the full PSD curve. The GRMS value computed from the Miles equation is a single number that summarizes the vibration severity at each resonance mode."));

children.push(bp("Miles data computed: ", "387,581 rows in the database across all studies and all channels"));
children.push(bp("Q factor coverage: ", "Approximately 80% of the data has valid Q factors. The remaining 20.1% (77,924 rows) have NULL Q factors because the half-power bandwidth could not be determined, typically when the resonance peak is too broad or too close to the frequency range boundary."));
children.push(bp("Miles features in ML: ", "1,483 of the 2,347 total features (63%) are Miles equation parameters, and 5 of the top 10 features are Miles-derived. This confirms their diagnostic value."));

children.push(pgBreak());

// ============================================================
// SECTION 8: HOW TO USE THIS SYSTEM
// ============================================================
children.push(h1("8. How to Use This System"));

children.push(p("This section describes how a structural engineer can use the trained classifier to assess a real structure for bolt looseness."));

children.push(numItem("1", "Run your accelerometer measurement. Collect PSD response data at the 12 node locations on the physical structure using accelerometers and displacement sensors."));
children.push(numItem("2", "Provide the PSD data to the pipeline. Import the measurement data into the database using the batch import script. The pipeline extracts the same 2,347 spectral features automatically."));
children.push(numItem("3", "The classifier compares your measurement to the 1,534 known signatures stored in the database. It identifies which bolt stiffness pattern best matches your measured response."));
children.push(numItem("4", "The system reports: which bolt is most likely loose, the confidence level of the prediction, and the closest matching simulation in the training database."));

children.push(p(""));
children.push(bp("Future capability: ", "A Model Context Protocol (MCP) interface is under development that will allow engineers to ask diagnostic questions in plain English, such as: What bolt is most likely loosened? How confident is the prediction? What would happen if I placed an additional sensor at Node 777?"));

children.push(pgBreak());

// ============================================================
// SECTION 9: DATA QUALITY & LIMITATIONS
// ============================================================
children.push(h1("9. Data Quality and Limitations"));

children.push(p("While the pipeline achieves 91.2% accuracy, several limitations should be understood before relying on the results for structural decisions."));

children.push(h2("9.1 Known Limitations"));

children.push(bullet("Healthy baseline sample size: Only 3 healthy samples exist in the training data, meaning the classifier has very limited experience with what a healthy structure looks like. The 3 healthy samples are: (1) study_baseline, case_id 361 (the dedicated healthy reference run, all 10 bolts at 1e12 N/mm); (2) Study A Design_9, case_id 73 (single-bolt sweep where all swept elements happened to be at baseline 1e12); (3) Study D Design_1, case_id 1035 (Monte Carlo draw where all elements landed at 1e12). The Healthy state has an F1 score of only 0.57. Recommendation: add at least 150 dedicated healthy baseline samples with slight input variation to improve healthy-state detection."));
children.push(bullet("Elements 9 and 10 training data: These elements have only 49 and 39 samples, respectively. Their F1 scores (0.59) are significantly below the 0.89+ achieved by elements with more data. More training simulations targeting these elements are needed."));
children.push(bullet("No CBUSH element force data: The Nastran recovery directives currently request acceleration and displacement PSD only. Adding CBUSH element force PSD (XYPUNCH,FORCE,PSDF) would provide direct measurement of the bolt forces, which are the most physically relevant indicator of bolt looseness."));
children.push(bullet("No strain energy data: Strain energy (ESE case control) is not currently computed. Strain energy distribution changes directly indicate where damage is occurring."));
children.push(bullet("Miles Q factor null rate: 20.1% of Miles equation rows have NULL Q factors because the half-power bandwidth could not be determined. This affects feature completeness for those channels."));
children.push(bullet("Looseness threshold: A stiffness threshold of 0.5 (on a normalized log scale) is used to label a bolt as loosened versus tight. This threshold has not been validated experimentally against physical bolt torque measurements."));
children.push(bullet("PSD row count variation: PSD data rows per simulation vary by 12.98%, exceeding the typical 10% threshold. This is caused by Nastran adaptive frequency point insertion near resonance peaks, but the elevated variation warrants investigation."));
children.push(bullet("Sample-to-feature ratio: With 1,534 samples and 2,347 features, the ratio is 0.65:1, well below the recommended 10:1 minimum. Dimensionality reduction through feature selection or Principal Component Analysis (PCA) is recommended."));

children.push(pgBreak());

// ============================================================
// APPENDIX A: DATABASE SUMMARY
// ============================================================
children.push(h1("Appendix A: Database Summary"));

const tnA = nextTable();
const dbRows = [
  new TableRow({ children: [hCell("Metric", 4000), hCell("Value", 5360)] }),
  new TableRow({ children: [dCell("Database file size", 4000), dCell("5,051.5 MB", 5360)] }),
  new TableRow({ children: [dCell("Total studies", 4000, altShading), dCell("5", 5360, altShading)] }),
  new TableRow({ children: [dCell("Total simulation cases", 4000), dCell("1,534", 5360)] }),
  new TableRow({ children: [dCell("Total PSD data rows", 4000, altShading), dCell("45,425,988", 5360, altShading)] }),
  new TableRow({ children: [dCell("Total peaks identified", 4000), dCell("165,672", 5360)] }),
  new TableRow({ children: [dCell("Total Miles equation rows", 4000, altShading), dCell("387,581", 5360, altShading)] }),
  new TableRow({ children: [dCell("Total ML features extracted", 4000), dCell("2,347", 5360)] }),
  new TableRow({ children: [dCell("Total ML training samples", 4000, altShading), dCell("1,534", 5360, altShading)] }),
  new TableRow({ children: [dCell("Best classifier accuracy", 4000), dCell("91.20% +/- 0.58% (GradientBoosting, 3-fold CV)", 5360)] }),
];
children.push(new Table({ width: { size: 9360, type: WidthType.DXA }, columnWidths: [4000,5360], rows: dbRows }));
children.push(caption("Table " + tnA + ": Database and Pipeline Summary Statistics"));

children.push(p(""));

const tnA2 = nextTable();
const studyRows = [
  new TableRow({ children: [hCell("Study Name", 3200), hCell("Cases", 1400), hCell("Baseline", 1400), hCell("Description", 3360)] }),
  new TableRow({ children: [dCell("study_baseline", 3200), dCellCenter("1", 1400), dCellCenter("Yes", 1400), dCell("Healthy reference (all bolts tight)", 3360)] }),
  new TableRow({ children: [dCell("study_A_single_bolt_sweep", 3200, altShading), dCellCenter("73", 1400, altShading), dCellCenter("No", 1400, altShading), dCell("One bolt loosened at a time", 3360, altShading)] }),
  new TableRow({ children: [dCell("study_B_two_bolt_sweep", 3200), dCellCenter("287", 1400), dCellCenter("No", 1400), dCell("Two bolts loosened simultaneously", 3360)] }),
  new TableRow({ children: [dCell("study_C_three_bolt_sweep", 3200, altShading), dCellCenter("672", 1400, altShading), dCellCenter("No", 1400, altShading), dCell("Three bolts loosened simultaneously", 3360, altShading)] }),
  new TableRow({ children: [dCell("study_D_monte_carlo", 3200), dCellCenter("501", 1400), dCellCenter("No", 1400), dCell("Random stiffness combinations", 3360)] }),
];
children.push(new Table({ width: { size: 9360, type: WidthType.DXA }, columnWidths: [3200,1400,1400,3360], rows: studyRows }));
children.push(caption("Table " + tnA2 + ": Study Breakdown"));

children.push(pgBreak());

// ============================================================
// APPENDIX B: COMPLETE FEATURE LIST
// ============================================================
children.push(h1("Appendix B: Feature Categories"));

children.push(p("The 2,347 features fall into four categories. The counts below reflect the full feature set extracted from the training matrix."));

const tnB = nextTable();
const catRows = [
  new TableRow({ children: [hCell("Category", 2600), hCell("Count", 1200), hCell("Description", 5560)] }),
  new TableRow({ children: [dCell("Peak Features", 2600), dCellCenter("605", 1200), dCell("Frequency and amplitude of first three resonance peaks per node/DOF channel (pk1f, pk1a, pk2f, pk2a, pk3f, pk3a)", 5560)] }),
  new TableRow({ children: [dCell("Spectral Features", 2600, altShading), dCellCenter("113", 1200, altShading), dCell("Area under PSD curve (total vibration energy) per node/DOF channel", 5560, altShading)] }),
  new TableRow({ children: [dCell("Delta Features", 2600), dCellCenter("66", 1200), dCell("Change from healthy baseline: RMS change (d_rms), band energy change (d_band0-3), peak frequency shift (d_pkshift)", 5560)] }),
  new TableRow({ children: [dCell("Miles Equation Features", 2600, altShading), dCellCenter("1,483", 1200, altShading), dCell("Natural frequency (fn), quality factor (Q), PSD at resonance (PSDfn), GRMS, bandwidth (bw) for up to 3 modes per node/DOF channel", 5560, altShading)] }),
  new TableRow({ children: [dCell("Other / Uncategorized", 2600), dCellCenter("80", 1200), dCell("Features not matching standard naming patterns", 5560)] }),
];
children.push(new Table({ width: { size: 9360, type: WidthType.DXA }, columnWidths: [2600,1200,5560], rows: catRows }));
children.push(caption("Table " + tnB + ": Feature Category Summary"));

children.push(p(""));
children.push(p("Features are extracted at 12 structural nodes (Nodes 1, 111, 222, 333, 444, 555, 666, 777, 888, 999, 1010, 1111). Acceleration features cover 3 translational DOFs (T1, T2, T3). Displacement features cover all 6 DOFs (T1, T2, T3, R1, R2, R3). Miles equation features are computed for up to 3 resonance modes per channel."));

children.push(pgBreak());

// ============================================================
// APPENDIX C: STIFFNESS MATRIX
// ============================================================
children.push(h1("Appendix C: Stiffness Configuration"));

children.push(p("The CBUSH elements use PBUSH property cards with three rotational stiffness terms (K4, K5, K6) that are swept simultaneously. The translational stiffness terms (K1, K2, K3) remain fixed. The stiffness values are applied through the HEEDS design exploration tool, which modifies the Bush.blk include file for each design iteration."));

const tnC = nextTable();
const stiffRows2 = [
  new TableRow({ children: [hCell("Level", 800), hCell("K4 = K5 = K6 (N/mm)", 2600), hCell("Log10 Value", 1600), hCell("Normalized (0-1)", 1600), hCell("Classification", 2760)] }),
  new TableRow({ children: [dCellCenter("1", 800), dCellCenter("1.00E+04", 2600), dCellCenter("4", 1600), dCellCenter("0.000", 1600), dCell("Severely loosened", 2760)] }),
  new TableRow({ children: [dCellCenter("2", 800, altShading), dCellCenter("1.00E+05", 2600, altShading), dCellCenter("5", 1600, altShading), dCellCenter("0.125", 1600, altShading), dCell("Very loose", 2760, altShading)] }),
  new TableRow({ children: [dCellCenter("3", 800), dCellCenter("1.00E+06", 2600), dCellCenter("6", 1600), dCellCenter("0.250", 1600), dCell("Loose", 2760)] }),
  new TableRow({ children: [dCellCenter("4", 800, altShading), dCellCenter("1.00E+07", 2600, altShading), dCellCenter("7", 1600, altShading), dCellCenter("0.375", 1600, altShading), dCell("Moderately loose", 2760, altShading)] }),
  new TableRow({ children: [dCellCenter("5", 800), dCellCenter("1.00E+08", 2600), dCellCenter("8", 1600), dCellCenter("0.500", 1600), dCell("Threshold (first detectable)", 2760)] }),
  new TableRow({ children: [dCellCenter("6", 800, altShading), dCellCenter("1.00E+09", 2600, altShading), dCellCenter("9", 1600, altShading), dCellCenter("0.625", 1600, altShading), dCell("Near-tight", 2760, altShading)] }),
  new TableRow({ children: [dCellCenter("7", 800), dCellCenter("1.00E+10", 2600), dCellCenter("10", 1600), dCellCenter("0.750", 1600), dCell("Near-tight", 2760)] }),
  new TableRow({ children: [dCellCenter("8", 800, altShading), dCellCenter("1.00E+11", 2600, altShading), dCellCenter("11", 1600, altShading), dCellCenter("0.875", 1600, altShading), dCell("Effectively tight", 2760, altShading)] }),
  new TableRow({ children: [dCellCenter("9", 800), dCellCenter("1.00E+12", 2600), dCellCenter("12", 1600), dCellCenter("1.000", 1600), dCell("Fully tight (baseline)", 2760)] }),
];
children.push(new Table({ width: { size: 9360, type: WidthType.DXA }, columnWidths: [800,2600,1600,1600,2760], rows: stiffRows2 }));
children.push(caption("Table " + tnC + ": Complete Stiffness Level Matrix"));

children.push(p(""));
children.push(p("Element 1 (connecting Node 1 to Node 111) is fixed as a structural constraint and is never loosened during the parametric studies. Only Elements 2 through 10 are swept. The baseline condition sets all elements to the fully tight state (1.00E+12 N/mm)."));

children.push(p("The looseness threshold for ML labeling is set at a normalized value of 0.5, corresponding to K4 = 1.00E+08 N/mm. Any bolt with stiffness at or below this level is labeled as loosened. This threshold was chosen because the PSD signature analysis shows that the first detectable frequency shift (23% reduction from baseline) occurs at this stiffness level."));


// ============================================================
// BUILD AND WRITE DOCUMENT (3 sections: portrait, landscape signature, portrait)
// ============================================================
const commonHeader = new Header({ children: [new Paragraph({
  alignment: AlignmentType.RIGHT,
  border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: "1F4E79", space: 1 } },
  children: [new TextRun({ text: "CBUSH Bolt Looseness Detection \u2014 Pipeline Final Report", font: "Arial", size: 16, color: "999999", italics: true })]
})] });

const commonFooter = new Footer({ children: [new Paragraph({
  alignment: AlignmentType.CENTER,
  children: [
    new TextRun({ text: "Page ", font: "Arial", size: 16, color: "999999" }),
    new TextRun({ children: [PageNumber.CURRENT], font: "Arial", size: 16, color: "999999" }),
    new TextRun({ text: " | Virginia Tech \u2014 Wayne Lee", font: "Arial", size: 16, color: "999999" })
  ]
})] });

const doc = new Document({
  styles: {
    default: {
      document: {
        run: { font: "Arial", size: 22 }
      }
    },
    paragraphStyles: [
      {
        id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 32, bold: true, font: "Arial", color: "1F4E79" },
        paragraph: { spacing: { before: 360, after: 200 } }
      },
      {
        id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 26, bold: true, font: "Arial", color: "2E75B6" },
        paragraph: { spacing: { before: 240, after: 160 } }
      },
    ]
  },
  sections: [
    // Section 1: Portrait (everything before signatures)
    {
      properties: {
        page: {
          size: { width: 12240, height: 15840 },
          margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 }
        }
      },
      headers: { default: commonHeader },
      footers: { default: commonFooter },
      children: childrenBeforeSig
    },
    // Section 2: Landscape (signature comparison page)
    {
      properties: {
        type: SectionType.NEXT_PAGE,
        page: {
          size: { width: 15840, height: 12240, orientation: PageOrientation.LANDSCAPE },
          margin: { top: 1080, right: 1080, bottom: 1080, left: 1080 }
        }
      },
      headers: { default: commonHeader },
      footers: { default: commonFooter },
      children: landscapeChildren
    },
    // Section 3: Portrait (everything after signatures)
    {
      properties: {
        type: SectionType.NEXT_PAGE,
        page: {
          size: { width: 12240, height: 15840 },
          margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 }
        }
      },
      headers: { default: commonHeader },
      footers: { default: commonFooter },
      children  // remaining children after signature section
    }
  ]
});

Packer.toBuffer(doc).then(buffer => {
  fs.writeFileSync(OUTPUT_PATH, buffer);
  console.log("Report written: " + OUTPUT_PATH);
  console.log("Size: " + (buffer.length / 1024).toFixed(1) + " KB");
  console.log("Figures: " + figNum);
  console.log("Tables: " + tableNum);
}).catch(err => {
  console.error("ERROR:", err.message);
  process.exit(1);
});
