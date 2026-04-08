% STN STOP/GO/SWITCH Task - Version 2 (matches protocol v1.1)
% Intraoperative, same-modality blocks (Visual, Auditory) with control miniblocks.
% Requires Psychtoolbox.
%
% Trial structure (per protocol):
%   Fixation 1000-1500 ms (jitter) after space is held ->
%   Movement cue (left/right arrow) 1000-1500 ms ->
%   GO cue (150 ms) and response window starts (1500 ms window from GO) ->
%   STOP or SWITCH cue after adaptive delay (SSD or SwSD), 150 ms duration.
%
% Blocks and counts:
%   Visual active:   60 GO, 20 STOP, 20 SWITCH  (100)
%   Visual control:  15 trials total (8 STOP-ignore, 7 SWITCH-ignore)
%   Auditory active: 60 GO, 20 STOP, 20 SWITCH  (100)
%   Auditory control:15 trials total (7 STOP-ignore, 8 SWITCH-ignore)
%
% Adaptive ladders (independent):
%   SSD start 200 ms, SwSD start 200 ms, step 50 ms, clamp [50, 900] ms.
%   STOP: success -> +50; fail -> -50.  SWITCH: correct -> +50; else -> -50.
%
% Key mapping: left response = keyboard '1!', right response = '2@'.
% SWITCH rule: press the opposite of the instructed arrow if SWITCH cue appears.

function data = STN_StopGoSwitch_v2(blockOrder, leftKeyName, rightKeyName)
    % blockOrder: 'visual_first' (default) or 'auditory_first'
    % leftKeyName/rightKeyName: optional KbName strings (default 'q'/'p')
    if nargin < 1, blockOrder = 'visual_first'; end
    if nargin < 2, leftKeyName = 'q'; end
    if nargin < 3, rightKeyName = 'p'; end

    KbName('UnifyKeyNames');
    keyLeft  = KbName(leftKeyName);
    keyRight = KbName(rightKeyName);
    escapeKey = KbName('ESCAPE');

    % Ladder params
    step = 0.050;
    minDelay = 0.050; maxDelay = 0.900;
    SSD  = struct('vis', 0.200, 'aud', 0.200);
    SwSD = struct('vis', 0.200, 'aud', 0.200);

    % Screen setup
    Screen('Preference','SkipSyncTests',1); % OR pilot safe; remove if sync OK
    screenNumber = max(Screen('Screens'));
    [w, rect] = Screen('OpenWindow', screenNumber, 0);
    Screen('TextFont', w, 'Arial');
    HideCursor;
    ListenChar(-1);

    % Colors and sizes
    white = [255 255 255];
    blue  = [0 122 255];
    orange = [255 140 0];
    fixSize = 80;
    arrowSize = 120;
    cueRadius = 60; % smaller GO/STOP/SWITCH cues

    % Trial schedule build
    blocks = buildBlocks(blockOrder);
    trials = [];
    for b = 1:numel(blocks)
        trials = [trials; blocks(b).trials]; %#ok<AGROW>
    end

    % Data containers
    n = numel(trials);
    data = struct([]);

    prevBlock = '';
    for t = 1:n
        tr = trials(t);
        if ~strcmp(prevBlock, tr.block)
            showBlockInstruction(w, tr.block, tr.context);
            prevBlock = tr.block;
        end
        % Select delay from current ladder
        if strcmp(tr.context,'visual')
            if strcmp(tr.type,'stop') || strcmp(tr.type,'stop_ignore')
                tr.delay = SSD.vis;
            elseif strcmp(tr.type,'switch') || strcmp(tr.type,'switch_ignore')
                tr.delay = SwSD.vis;
            end
        else
            if strcmp(tr.type,'stop') || strcmp(tr.type,'stop_ignore')
                tr.delay = SSD.aud;
            elseif strcmp(tr.type,'switch') || strcmp(tr.type,'switch_ignore')
                tr.delay = SwSD.aud;
            end
        end

    % Hold space to start trial
    drawOverlay(w, rect, sprintf('%d/%d', t, n));
    Screen('TextSize', w, fixSize);
    DrawFormattedText(w, 'Hold SPACE to start', 'center','center', white);
    Screen('Flip', w);
    while true
        [pressed, pressTime, keyCode] = KbCheck;
        if pressed && keyCode(KbName('SPACE'))
            spaceDownTime = pressTime;
            break;
        end
    end

    % Fixation (starts once space held)
    drawFix(w, rect, white, fixSize, t, n);
    WaitSecs(tr.fix);

    % Movement cue (arrow offset to left/right half)
    drawArrow(w, rect, tr.dir, white, arrowSize, t, n);
    WaitSecs(tr.move);

    % GO cue onset
    drawCircle(w, rect, white, cueRadius, t, n);
    goOn = Screen('Flip', w);
    rtSpace = NaN; rt = NaN; resp = NaN; success = NaN;

    cueOn = NaN; cueType = tr.type; cueShown = false;
    stopDeadline = goOn + 1.5; % for stop and go
    switchDeadline = NaN;

    % Response loop with cue scheduling
    while true
        nowT = GetSecs;
        % Show stop/switch cue when its time
        if ~cueShown && ismember(cueType, {'stop','switch','stop_ignore','switch_ignore'}) && nowT - goOn >= tr.delay
            if strcmp(cueType,'stop') || strcmp(cueType,'stop_ignore')
                drawCircle(w, rect, blue, cueRadius, t, n);
            else
                drawCircle(w, rect, orange, cueRadius, t, n);
            end
            cueOn = Screen('Flip', w);
            cueShown = true;
            if strcmp(cueType,'switch')
                switchDeadline = cueOn + 1.5;
            end
        end

        [pressed, pressTime, keyCode] = KbCheck;
        if pressed
            if keyCode(escapeKey), abort(w); end
            if isnan(resp)
                if keyCode(keyLeft), resp = 1; rt = pressTime - goOn; end
                if keyCode(keyRight), resp = 2; rt = pressTime - goOn; end
                if ~isnan(resp), break; end
            end
        else
            keyCode = zeros(size(keyCode));
        end
        % space release detection (even if no other key pressed)
        if isnan(rtSpace) && ~isempty(spaceDownTime) && ~keyCode(KbName('SPACE')) && nowT > goOn
            rtSpace = nowT - goOn;
        end

        % timeouts
        if strcmp(cueType,'switch') && ~isnan(switchDeadline) && nowT >= switchDeadline
            break;
        elseif ~strcmp(cueType,'switch') && nowT >= stopDeadline
            break;
        end
        WaitSecs(0.001);
    end
    if isnan(rt), rt = NaN; end
    if isnan(rtSpace), rtSpace = NaN; end

        % Determine correctness and update ladders
        success = computeOutcome(tr, resp);
    if ~tr.isControl
        if strcmp(tr.context,'visual')
            if strcmp(cueType,'stop')
                SSD.vis = clampDelay(SSD.vis + step*adaptStep(success), minDelay, maxDelay);
            elseif strcmp(cueType,'switch')
                SwSD.vis = clampDelay(SwSD.vis + step*adaptStep(success), minDelay, maxDelay);
                end
            else
                if strcmp(cueType,'stop')
                    SSD.aud = clampDelay(SSD.aud + step*adaptStep(success), minDelay, maxDelay);
                elseif strcmp(cueType,'switch')
                    SwSD.aud = clampDelay(SwSD.aud + step*adaptStep(success), minDelay, maxDelay);
                end
            end
        end

    % Brief buffer after failed stop/switch to show cue
    if ismember(cueType, {'stop','switch'}) && ~isnan(resp)
        WaitSecs(0.2);
    end

    % Log trial
    data(t).block      = tr.block;
        data(t).context    = tr.context;
        data(t).type       = tr.type;
        data(t).dir        = tr.dir;
        data(t).delay_used = tr.delay;
        data(t).ssd_vis    = SSD.vis;   % ladder snapshot after update
        data(t).ssd_aud    = SSD.aud;
        data(t).swsd_vis   = SwSD.vis;
        data(t).swsd_aud   = SwSD.aud;
        data(t).resp       = resp;
        data(t).rt         = rt;
        data(t).rt_space   = rtSpace;
        data(t).success    = success;
        data(t).go_onset   = goOn;
        data(t).cue_onset  = cueOn;
    end

    ShowCursor; ListenChar(0); Screen('CloseAll');
end

function blocks = buildBlocks(order)
    blocks = struct([]);
    seq = {'visual','auditory'};
    if strcmp(order,'auditory_first'), seq = {'auditory','visual'}; end
    idx = 1;
    for s = 1:2
        ctx = seq{s};
        blocks(idx) = makeActiveBlock(ctx); idx = idx + 1; %#ok<AGROW>
        blocks(idx) = makeControlBlock(ctx); idx = idx + 1; %#ok<AGROW>
    end
end

function b = makeActiveBlock(ctx)
    % Blocked design: STOP block then SWITCH block to reduce cognitive load.
    stopTypes = [repmat({'go'},1,30), repmat({'stop'},1,20)];
    switchTypes = [repmat({'go'},1,30), repmat({'switch'},1,20)];
    stopTypes = stopTypes(randperm(numel(stopTypes)));
    switchTypes = switchTypes(randperm(numel(switchTypes)));

    trialsStop = arrayfun(@(k) makeTrial(stopTypes{k}, ctx, false, [ctx '_active_stopblock']), 1:numel(stopTypes));
    trialsSwitch = arrayfun(@(k) makeTrial(switchTypes{k}, ctx, false, [ctx '_active_switchblock']), 1:numel(switchTypes));

    b.block = [ctx '_active'];
    b.trials = [trialsStop, trialsSwitch]';
    % Insert instruction callbacks by tagging block name; handled in main loop.
end

function showBlockInstruction(w, blockName, ctx)
    if contains(blockName, 'stopblock')
        line1 = 'STOP block: cancel response if STOP appears.';
    elseif contains(blockName, 'switchblock')
        line1 = 'SWITCH block: press the opposite button if SWITCH appears.';
    else
        line1 = 'CONTROL block: ignore later cues; respond to GO.';
    end
    if strcmp(ctx,'visual')
        line2 = 'Visual cues: STOP = blue circle, SWITCH = orange circle.';
    else
        line2 = 'Auditory cues: STOP = high tone, SWITCH = low tone.';
    end
    Screen('TextSize', w, 36);
    DrawFormattedText(w, sprintf('%s\n\n%s\n%s\n\nPress any key to continue.', blockName, line1, line2), 'center','center', 255);
    Screen('Flip', w);
    KbStrokeWait;
end

function b = makeControlBlock(ctx)
    % STOP-ignore and SWITCH-ignore counts per protocol
    stopN = strcmp(ctx,'visual')*8 + strcmp(ctx,'auditory')*7;
    switchN = strcmp(ctx,'visual')*7 + strcmp(ctx,'auditory')*8;
    types = [repmat({'stop_ignore'},1,stopN), repmat({'switch_ignore'},1,switchN)];
    types = types(randperm(numel(types)));
    trials = arrayfun(@(k) makeTrial(types{k}, ctx, true, [ctx '_control']), 1:numel(types));
    b.block = [ctx '_control'];
    b.trials = trials';
end

function tr = makeTrial(type, ctx, isControl, blockName)
    tr.type = type;
    tr.context = ctx;
    tr.block = blockName;
    tr.dir = ternary(rand < 0.5, 'left', 'right');
    tr.fix = 1.0 + rand*0.5;  % 1.0–1.5 s
    tr.move = 1.0 + rand*0.5; % 1.0–1.5 s
    % Delays chosen from current ladder at runtime; placeholder set now
    tr.delay = 0.200;
    tr.isControl = isControl;
end

function drawFix(w, rect, color, sz, trialIdx, total)
    Screen('TextSize', w, sz);
    DrawFormattedText(w, '+', 'center','center', color);
    drawOverlay(w, rect, trialIdx, total);
    Screen('Flip', w);
end

function drawArrow(w, rect, dir, color, sz, trialIdx, total)
    Screen('TextSize', w, sz);
    [cx, cy] = RectCenter(rect);
    if strcmp(dir,'left')
        x = rect(1) + (rect(3)-rect(1))*0.25;
        DrawFormattedText(w, '\leftarrow', x, cy-0.5*sz, color);
    else
        x = rect(1) + (rect(3)-rect(1))*0.75;
        DrawFormattedText(w, '\rightarrow', x, cy-0.5*sz, color);
    end
    drawOverlay(w, rect, trialIdx, total);
    Screen('Flip', w);
end

function drawCircle(w, rect, color, radius, trialIdx, total)
    [cx, cy] = RectCenter(rect);
    base = [cx-radius, cy-radius, cx+radius, cy+radius];
    Screen('FillOval', w, color, base);
    drawOverlay(w, rect, trialIdx, total);
end

function val = clampDelay(v, lo, hi)
    val = max(lo, min(hi, v));
end

function stepDir = adaptStep(success)
    if success, stepDir = 1; else, stepDir = -1; end
end

function success = computeOutcome(tr, resp)
    switch tr.type
        case 'go'
            success = ~isnan(resp) && ((strcmp(tr.dir,'left') && resp==1) || (strcmp(tr.dir,'right') && resp==2));
        case 'stop'
            success = isnan(resp);
        case 'switch'
            if strcmp(tr.dir,'left')
                success = ~isnan(resp) && resp==2;
            else
                success = ~isnan(resp) && resp==1;
            end
        case {'stop_ignore','switch_ignore'}
            % Always respond as GO; success if responded with instructed direction
            success = ~isnan(resp) && ((strcmp(tr.dir,'left') && resp==1) || (strcmp(tr.dir,'right') && resp==2));
        otherwise
            success = false;
    end
end

function out = ternary(cond, a, b)
    if cond, out = a; else, out = b; end
end

function abort(w)
    ShowCursor; ListenChar(0); Screen('CloseAll'); error('User aborted.');
end

function drawOverlay(w, rect, trialIdx, total)
    Screen('TextSize', w, 20);
    DrawFormattedText(w, sprintf('%d/%d', trialIdx, total), rect(3)-150, rect(2)+20, [200 200 200]);
end
