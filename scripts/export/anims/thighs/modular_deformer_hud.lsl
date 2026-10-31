// ==============================================================================
// Modular Second Life Avatar Deformer HUD Script
// Controls independent deformation channels (Position, Rotation, Scale).
// Plays Priority 5 looped animations concurrently on the avatar.
// ==============================================================================

integer CHANNEL_DIALOG = -884422;
integer gListener;
key gOwner;

// Track active animation per channel
// Channels: 0:PosX, 1:PosY, 2:PosZ, 3:RotX, 4:RotY, 5:RotZ, 6:ScaleVol, 7:ScaleLen
list gActiveAnims = ["", "", "", "", "", "", "", ""];
list gStepIndices = [0, 0, 0, 0, 0, 0, 0, 0];
list gChannelNames = [
    "Pos_X", "Pos_Y", "Pos_Z",
    "Rot_X", "Rot_Y", "Rot_Z",
    "Scale_Vol", "Scale_Len"
];

integer gCurrentChannel = 1; // Default to Pos_Y (Thigh Gap)
integer MAX_STEPS = 10;

string getAnimName(integer ch_idx, integer step) {
    if (step == 0) return "";
    string ch = llList2String(gChannelNames, ch_idx);
    string prefix = "p";
    if (step < 0) {
        prefix = "m";
        step = -step;
    }
    string sStep = (string)step;
    if (step < 10) sStep = "0" + sStep;
    return "Thigh_" + ch + "_" + prefix + sStep;
}

setChannelStep(integer ch_idx, integer new_step) {
    if (new_step > MAX_STEPS) new_step = MAX_STEPS;
    if (new_step < -MAX_STEPS) new_step = -MAX_STEPS;
    
    integer old_step = llList2Integer(gStepIndices, ch_idx);
    if (old_step == new_step) return;
    
    string old_anim = llList2String(gActiveAnims, ch_idx);
    string new_anim = getAnimName(ch_idx, new_step);
    
    // Stop old animation on this channel
    if (old_anim != "" && llGetInventoryType(old_anim) == INVENTORY_ANIMATION) {
        llStopAnimation(old_anim);
    }
    
    // Play new animation on this channel
    if (new_anim != "" && llGetInventoryType(new_anim) == INVENTORY_ANIMATION) {
        llStartAnimation(new_anim);
    }
    
    gActiveAnims = llListReplaceList(gActiveAnims, [new_anim], ch_idx, ch_idx);
    gStepIndices = llListReplaceList(gStepIndices, [new_step], ch_idx, ch_idx);
    
    llOwnerSay("Channel [" + llList2String(gChannelNames, ch_idx) + "] -> Step " + (string)new_step);
}

resetAll() {
    integer i;
    for (i = 0; i < 8; ++i) {
        string anim = llList2String(gActiveAnims, i);
        if (anim != "" && llGetInventoryType(anim) == INVENTORY_ANIMATION) {
            llStopAnimation(anim);
        }
    }
    gActiveAnims = ["", "", "", "", "", "", "", ""];
    gStepIndices = [0, 0, 0, 0, 0, 0, 0, 0];
    llOwnerSay("All deformer channels reset to skeleton default.");
}

showMenu() {
    string ch_name = llList2String(gChannelNames, gCurrentChannel);
    integer current_step = llList2Integer(gStepIndices, gCurrentChannel);
    
    string text = "\n=== THIGH DEFORMER HUD ===\n" +
                  "Current Channel: [" + ch_name + "]\n" +
                  "Active Step: " + (string)current_step + " / " + (string)MAX_STEPS + "\n\n" +
                  "Select an action or change channel:";
                  
    list buttons = [
        "- Step", "Reset Ch", "+ Step",
        "Select Ch", "Reset All", "Close"
    ];
    llDialog(gOwner, text, buttons, CHANNEL_DIALOG);
}

showChannelMenu() {
    string text = "\nSelect Deformer Channel to Adjust:";
    list buttons = [
        "Pos_X", "Pos_Y", "Pos_Z",
        "Rot_X", "Rot_Y", "Rot_Z",
        "Scale_Vol", "Scale_Len", "<< Back"
    ];
    llDialog(gOwner, text, buttons, CHANNEL_DIALOG);
}

default {
    state_entry() {
        gOwner = llGetOwner();
        llRequestPermissions(gOwner, PERMISSION_TRIGGER_ANIMATION);
    }
    
    run_time_permissions(integer perm) {
        if (perm & PERMISSION_TRIGGER_ANIMATION) {
            llOwnerSay("Deformer HUD ready. Touch HUD to open controls.");
        }
    }
    
    attach(key id) {
        if (id != NULL_KEY) {
            gOwner = id;
            llRequestPermissions(gOwner, PERMISSION_TRIGGER_ANIMATION);
        } else {
            resetAll();
        }
    }
    
    touch_start(integer total_number) {
        if (llDetectedKey(0) != gOwner) return;
        llListenRemove(gListener);
        CHANNEL_DIALOG = (integer)(llFrand(-999999.0) - 100000.0);
        gListener = llListen(CHANNEL_DIALOG, "", gOwner, "");
        showMenu();
    }
    
    listen(integer channel, string name, key id, string msg) {
        if (id != gOwner) return;
        
        if (msg == "Close") {
            llListenRemove(gListener);
            return;
        }
        else if (msg == "+ Step") {
            integer cur = llList2Integer(gStepIndices, gCurrentChannel);
            setChannelStep(gCurrentChannel, cur + 1);
            showMenu();
        }
        else if (msg == "- Step") {
            integer cur = llList2Integer(gStepIndices, gCurrentChannel);
            setChannelStep(gCurrentChannel, cur - 1);
            showMenu();
        }
        else if (msg == "Reset Ch") {
            setChannelStep(gCurrentChannel, 0);
            showMenu();
        }
        else if (msg == "Reset All") {
            resetAll();
            showMenu();
        }
        else if (msg == "Select Ch") {
            showChannelMenu();
        }
        else if (msg == "<< Back") {
            showMenu();
        }
        else {
            // Check if msg matches a channel name
            integer idx = llListFindList(gChannelNames, [msg]);
            if (idx != -1) {
                gCurrentChannel = idx;
                showMenu();
            }
        }
    }
}
