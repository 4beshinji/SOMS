// ================================================================
// SOMS Sensor Node — BME680-Only Test Configuration
// ================================================================
//
// Minimal test build: XIAO ESP32-C6 + BME680 only
// 2-chamber thermal separation retained for validation
// No PIR, no CO2 sensor, no fan
//
// Orientation:
//   +Y = front (vent face, faces room)
//   -Y = back  (wall-mount keyholes)
//   +X = right (USB-C exit)
//    Z = up    (exhaust)
// ================================================================

// ======================== RENDER TARGET ==========================
// "assembly"   Exploded assembly view
// "bottom"     Sensor chamber (print as-is)
// "top"        MCU chamber (print flipped)
// "all_plate"  All parts on print plate
part = "assembly";

// ======================== PARAMETERS ============================

// --- Print: Ender 3 KE, PLA, 0.4mm nozzle ---
wall    = 1.6;      // 0.4mm × 4 perimeters
tol     = 0.25;     // PLA tolerance per side
$fn     = 64;

// --- Components [W, D, H] ---
// Seeed XIAO ESP32-C6
XIAO        = [21, 17.5, 3.5];
XIAO_USB    = [9, 7.5, 3.5];
XIAO_PIN_H  = 2.5;             // pin header below board

// BME680 breakout (e.g. GY-BME680 / CJMCU-680)
BME680      = [15, 12, 3];

// JST-XH 2.5mm — 4-pin only (VCC, GND, SDA, SCL)
XH_4P       = [12.5, 5.75, 7];

// --- Chamber internals [W, D, H] ---
// Height budget (sensor):  standoff 4 + PCB 1.6 + XH header 7 + clearance 3.4 = 16
// Height budget (MCU):     standoff 4 + PCB 1.6 + spacer 2.5 + XIAO 3.5
//                          + pin tip 2.5 + clearance 3.9 = 18
//   (XIAO has pin headers soldered — total above PCB: 2.5+3.5+2.5 = 8.5mm)
SENS_INT    = [28, 22, 16];     // sensor chamber (perfboard + BME680 + XH-4P)
MCU_INT     = [28, 22, 18];     // MCU chamber (XIAO w/ pin headers + XH-4P)

// --- Thermal barrier ---
BAR_SOLID   = 3;
BAR_AIR     = 5;
CABLE_PASS  = [10, 5];          // 4-wire harness pass-through

// --- Chassis outer (derived) ---
CW = MCU_INT.x + 2 * wall;     // 31.2mm
CD = MCU_INT.y + 2 * wall;     // 25.2mm

BH  = wall + SENS_INT.z + BAR_SOLID;   // bottom: 16.6mm
TH  = MCU_INT.z + wall;                // top:    16.6mm
TOTAL_H = BH + BAR_AIR + TH;           // total:  38.2mm

// --- M2 fasteners ---
M2_THRU     = 2.4;
M2_INSERT   = 3.2;
M2_INS_DEP  = 4;
M2_HEAD     = 4.2;
M2_HEAD_H   = 2.0;

// Boss positions — 4 corners
BOSS_INSET  = 5;
BOSS = [
    [ CW/2 - BOSS_INSET,  CD/2 - BOSS_INSET],
    [-CW/2 + BOSS_INSET,  CD/2 - BOSS_INSET],
    [ CW/2 - BOSS_INSET, -CD/2 + BOSS_INSET],
    [-CW/2 + BOSS_INSET, -CD/2 + BOSS_INSET]
];

// --- Wall mount ---
KH_BIG      = 6;
KH_SLOT     = 3.5;
KH_SPACE    = 18;               // narrower spacing for small chassis

// --- Ventilation ---
VSLOT_W     = 2.0;
VSLOT_GAP   = 3.0;

// ======================== DIMENSION REPORT =======================
echo("=== BME680-only test config ===");
echo(str("  Chassis W×D×H: ", CW, " × ", CD, " × ", TOTAL_H, " mm"));
echo(str("  Bottom half:   ", BH, " mm"));
echo(str("  Air gap:       ", BAR_AIR, " mm"));
echo(str("  Top half:      ", TH, " mm"));

// ======================== UTILITIES ==============================

module rbox(size, r = 2) {
    hull()
        for (sx = [-1, 1], sy = [-1, 1])
            translate([sx * (size.x/2 - r), sy * (size.y/2 - r), 0])
                cylinder(r = r, h = size.z);
}

module slot_array(span, slot_w, slot_h, depth = 10) {
    n = max(1, floor(span / (slot_w + VSLOT_GAP)));
    total = n * slot_w + (n - 1) * VSLOT_GAP;
    x0 = -total / 2 + slot_w / 2;
    for (i = [0 : n - 1])
        translate([x0 + i * (slot_w + VSLOT_GAP), 0, 0])
            cube([slot_w, depth, slot_h], center = true);
}

module hex_grid(w, h, hex_r = 2.5, pitch = 7) {
    dx = pitch * 1.5;
    dy = pitch * sin(60);
    for (cx = [-ceil(w / dx / 2) : ceil(w / dx / 2)])
        for (cy = [-ceil(h / dy / 2) : ceil(h / dy / 2)]) {
            px = cx * dx;
            py = cy * dy + (abs(cx) % 2) * dy / 2;
            if (abs(px) < w/2 - hex_r && abs(py) < h/2 - hex_r)
                translate([px, py, 0])
                    cylinder(r = hex_r, h = wall * 3, center = true, $fn = 6);
        }
}

module keyhole_2d(d_big, d_slot) {
    circle(d = d_big);
    translate([d_big * 0.35, 0])
        circle(d = d_slot);
    translate([0, -d_slot / 2])
        square([d_big * 0.7, d_slot]);
}


// ======================== BOTTOM HALF ============================
// Sensor chamber (BME680 only) + thermal barrier ceiling

module bottom_half() {
    difference() {
        // --- Solid body ---
        rbox([CW, CD, BH]);

        // --- Sensor chamber cavity ---
        translate([0, 0, wall])
            rbox([SENS_INT.x, SENS_INT.y, SENS_INT.z + 0.1], r = 1);

        // --- Side vents (all 4 faces for BME680 airflow) ---
        // BME680 needs ambient air for temp/humidity/VOC accuracy
        vent_z_lo = wall + 3;
        vent_z_hi = wall + SENS_INT.z - 3;
        vent_h = vent_z_hi - vent_z_lo;
        vent_z_mid = (vent_z_lo + vent_z_hi) / 2;

        // Left/right (±X)
        for (sx = [-1, 1])
            translate([sx * CW / 2, 0, vent_z_mid])
                rotate([0, 0, 0])
                slot_array(SENS_INT.y - 6, VSLOT_W, vent_h, wall + 2);

        // Front/back (±Y)
        for (sy = [-1, 1])
            translate([0, sy * CD / 2, vent_z_mid])
                rotate([0, 0, 90])
                slot_array(SENS_INT.x - 6, VSLOT_W, vent_h, wall + 2);

        // --- Cable pass-through (barrier ceiling) ---
        translate([0, 0, BH - BAR_SOLID / 2])
            cube([CABLE_PASS.x, CABLE_PASS.y, BAR_SOLID + 0.2],
                 center = true);

        // --- M2 heat-set insert holes ---
        for (p = BOSS)
            translate([p.x, p.y, BH - M2_INS_DEP])
                cylinder(d = M2_INSERT, h = M2_INS_DEP + 0.1);

        // --- Keyholes (back face -Y) ---
        for (dx = [-KH_SPACE / 2, KH_SPACE / 2])
            translate([dx, -CD / 2 - 0.1, BH * 0.45])
                rotate([90, 0, 0])
                rotate([0, 0, 90])
                linear_extrude(wall + 0.2)
                    keyhole_2d(KH_BIG, KH_SLOT);
    }

    // --- Universal PCB mount (perfboard ~25×20mm) ---
    // 4 corner standoffs: height = 4mm (clears XH header pins below board)
    pcb_standoff = 4;
    pcb_w = 25;         // perfboard width (cut to fit)
    pcb_d = 20;         // perfboard depth (cut to fit)
    for (dx = [-1, 1], dy = [-1, 1])
        translate([dx * (pcb_w / 2 - 2),
                   dy * (pcb_d / 2 - 2),
                   wall])
            difference() {
                cylinder(d = 4, h = pcb_standoff, $fn = 20);
                // M2 self-tap hole for optional screw fixing
                translate([0, 0, -0.1])
                    cylinder(d = 1.8, h = pcb_standoff + 0.2, $fn = 20);
            }

    // Side rails for PCB edge support (along X axis)
    for (dy = [-1, 1])
        translate([-pcb_w / 2, dy * (pcb_d / 2 + 0.3) - 0.75, wall])
            cube([pcb_w, 1.5, pcb_standoff]);
}


// ======================== TOP HALF ===============================
// MCU chamber (XIAO ESP32-C6) + standoffs for air gap

module top_half() {
    difference() {
        union() {
            // --- Main body ---
            rbox([CW, CD, TH]);

            // --- Standoff posts (air gap spacers) ---
            for (p = BOSS)
                translate([p.x, p.y, -BAR_AIR])
                    cylinder(d = M2_THRU + 4, h = BAR_AIR + 0.01, $fn = 20);
        }

        // --- MCU chamber cavity ---
        translate([0, 0, -0.01])
            rbox([MCU_INT.x, MCU_INT.y, MCU_INT.z + 0.01], r = 1);

        // --- Top hex ventilation (MCU exhaust) ---
        translate([0, 0, TH - wall / 2])
            hex_grid(CW - 8, CD - 8, hex_r = 2, pitch = 6);

        // --- Side vents (left/right ±X) ---
        for (sx = [-1, 1])
            translate([sx * CW / 2, 0, MCU_INT.z / 2])
                slot_array(MCU_INT.y - 6, VSLOT_W, MCU_INT.z - 6,
                           wall + 2);

        // --- USB-C port cutout (right side +X) ---
        usb_z = XIAO_PIN_H + XIAO.z / 2;
        translate([CW / 2 - wall / 2, 0, usb_z])
            cube([wall + 1, XIAO_USB.x + 2, XIAO_USB.z + 2],
                 center = true);

        // --- M2 through holes + countersink ---
        for (p = BOSS) {
            translate([p.x, p.y, -BAR_AIR - 0.1])
                cylinder(d = M2_THRU, h = BAR_AIR + TH + 0.2);
            translate([p.x, p.y, -BAR_AIR - 0.1])
                cylinder(d = M2_HEAD, h = M2_HEAD_H + 0.1);
        }

        // --- Harness entry hole (from barrier below) ---
        translate([0, 0, -0.1])
            cube([CABLE_PASS.x + 2, CABLE_PASS.y + 2, 3],
                 center = true);
    }

    // --- Universal PCB mount (perfboard ~25×20mm) ---
    // Standoffs: 4mm (clears XH header pins below board)
    mcu_standoff = 4;
    mcu_pcb_w = 25;
    mcu_pcb_d = 20;
    for (dx = [-1, 1], dy = [-1, 1])
        translate([dx * (mcu_pcb_w / 2 - 2),
                   dy * (mcu_pcb_d / 2 - 2),
                   0])
            difference() {
                cylinder(d = 4, h = mcu_standoff, $fn = 20);
                translate([0, 0, -0.1])
                    cylinder(d = 1.8, h = mcu_standoff + 0.2, $fn = 20);
            }

    // Side rails for PCB edge support
    for (dy = [-1, 1])
        translate([-mcu_pcb_w / 2, dy * (mcu_pcb_d / 2 + 0.3) - 0.75, 0])
            cube([mcu_pcb_w, 1.5, mcu_standoff]);
}


// ======================== ASSEMBLY ===============================

module assembly() {
    explode = 6;

    // Bottom half
    color("DimGray")
        bottom_half();

    // Top half
    color("SlateGray")
        translate([0, 0, BH + BAR_AIR + explode])
        top_half();

    // --- Ghost components ---
    // BME680 (in sensor chamber)
    %color("Purple", 0.4)
        translate([0, 0, wall + 2 + BME680.z / 2])
        cube(BME680, center = true);

    // XIAO ESP32-C6 (in MCU chamber)
    xiao_z = BH + BAR_AIR + explode + XIAO_PIN_H;
    xiao_cx = CW / 2 - wall - XIAO.x / 2 - 1;
    %color("SeaGreen", 0.4)
        translate([xiao_cx, 0, xiao_z + XIAO.z / 2])
        cube(XIAO, center = true);

    // Dimensional reference lines
    echo(str("TOTAL assembled height: ", TOTAL_H, " mm"));
}


// ======================== RENDER =================================

if (part == "assembly") {
    assembly();
}
else if (part == "bottom") {
    bottom_half();
}
else if (part == "top") {
    // Print: ceiling on bed, standoffs + cavity facing up
    translate([0, 0, TH])
        rotate([180, 0, 0])
        top_half();
}
else if (part == "all_plate") {
    // Both parts on print plate, spaced apart
    translate([-CW / 2 - 3, 0, 0])
        bottom_half();
    translate([CW / 2 + 3, 0, TH])
        rotate([180, 0, 0])
        top_half();
}
