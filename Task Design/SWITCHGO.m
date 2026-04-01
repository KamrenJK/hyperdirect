% ==============================================================
% GO-SWITCH SIGNAL TASK (minimal working demo)
% GO cue: press 1 or 2 as fast as possible
% SWITCH cue (on a subset of trials): press the OTHER button instead
% SWITCH cue modality: visual (green arrow) or auditory (different tone)
%
% Independent SSD ladders for VISUAL vs AUDITORY switch cues.
%
% Ladder rule (recommended for SWITCH):
%   SUCCESSFUL switch (final response is correct switched button) -> SSD increases (+step) (harder next time)
%   FAILED switch (wrong final button or no response)             -> SSD decreases (-step) (easier next time)
%
% Tracks SSD over time for both modalities, prints timing summary,
% and plots ladder evolution.
% ==============================================================

clear; clc; close all
KbName('UnifyKeyNames');

%% experiment parameters
cfg.ntrials    = 120;
cfg.switchFrac = 0.36;

cfg.fixMin     = 1.5;
cfg.fixMax     = 2.0;

cfg.respWindow = 1.5;      % time from GO onset to respond (switch must occur within this)
cfg.iti        = 0.3;

cfg.ssdStart   = 0.300;
cfg.ssdStep    = 0.050;

cfg.ssdMin     = 0.055;
cfg.ssdMax     = 1.000;

% text sizes (kept constant)
cfg.goTextSize     = 120;  % fixation and GO digit
cfg.switchTextSize = 160;  % SWITCH arrow

%% keys
key1 = KbName('1!');
key2 = KbName('2@');
escapeKey = KbName('ESCAPE');

%% trial schedule
isSwitch = rand(cfg.ntrials,1) < cfg.switchFrac;

SWITCH_VIS = 1;
SWITCH_AUD = 2;

switchType = nan(cfg.ntrials,1);
switchIdx  = find(isSwitch);
nSwitch    = length(switchIdx);

% Balance auditory vs visual within switch trials
tmp = [repmat(SWITCH_VIS, ceil(nSwitch/2), 1); repmat(SWITCH_AUD, floor(nSwitch/2), 1)];
tmp = tmp(randperm(length(tmp)));
switchType(switchIdx) = tmp(1:nSwitch);

goInstr = randi([1 2], cfg.ntrials, 1);
fixLag  = cfg.fixMin + rand(cfg.ntrials,1)*(cfg.fixMax - cfg.fixMin);

% correct response:
% - if no switch: correct = goInstr
% - if switch: correct = 3 - goInstr (swap 1<->2)
correctResp = goInstr;
correctResp(isSwitch) = 3 - goInstr(isSwitch);

%% ladders (independent)
ssd_vis = cfg.ssdStart;
ssd_aud = cfg.ssdStart;

%% audio cues
InitializePsychSound(1);
fs = 44100;

% SWITCH tone: make it distinct from any STOP tone you used (lower + wobble)
toneDur = 0.15;
toneAmp = 0.75;
t = 0:1/fs:toneDur;

% A "wobbly" inharmonic chord to stand out
switchTone = ...
    sin(2*pi*520*t) + ...
    sin(2*pi*790*t) + ...
    sin(2*pi*1230*t);

% add slight roughness (AM) for salience
am = 1 + 0.35*sin(2*pi*70*t);
switchTone = switchTone .* am;

switchTone = switchTone / max(abs(switchTone));
switchTone = switchTone * toneAmp;

pahandle = PsychPortAudio('Open', [], 1, 1, fs, 1);

%% screen (debug windowed)
screenNumber = max(Screen('Screens'));
debugRect = [200 200 1000 800];

Screen('Preference','SkipSyncTests',1);       % OK for debugging
Screen('Preference','VisualDebugLevel',1);    % removes startup splash
Screen('Preference','Verbosity',2);

[w, rect] = Screen('OpenWindow', screenNumber, 0, debugRect);
Screen('TextFont', w, 'Arial');

Priority(0);
ListenChar(-1);
HideCursor;

%% instructions
Screen('TextSize', w, 32);
DrawFormattedText(w, ...
    ['Press 1 when you see "1"\n' ...
     'Press 2 when you see "2"\n\n' ...
     'On some trials you will get a SWITCH cue.\n' ...
     'If you see a GREEN ARROW or hear a different tone,\n' ...
     'press the OTHER button instead.\n\n' ...
     'Press any key to start'], ...
    'center','center',255);
Screen('Flip', w);
KbStrokeWait;

%% allocate data
rt           = nan(cfg.ntrials,1);   % RT relative to GO onset of FINAL response
resp         = nan(cfg.ntrials,1);   % final response (1/2)
wasCorrect   = nan(cfg.ntrials,1);   % correct final response?

% switch performance
switchSuccess = nan(cfg.ntrials,1);  % for switch trials only

goOn        = nan(cfg.ntrials,1);
switchOn    = nan(cfg.ntrials,1);    % onset timestamp (Flip time or audio start time)
ssdUsed     = nan(cfg.ntrials,1);    % SSD used on that trial (switch trials only)

% SSD ladder values over time (snapshot each trial)
ssdVisOverTime = nan(cfg.ntrials,1);
ssdAudOverTime = nan(cfg.ntrials,1);

% trial durations
trialStartT = nan(cfg.ntrials,1);
trialEndT   = nan(cfg.ntrials,1);

%% timing: whole experiment
expStart = GetSecs;

%% trial loop
for tr = 1:cfg.ntrials

    trialStartT(tr) = GetSecs;

    % snapshot current ladder values
    ssdVisOverTime(tr) = ssd_vis;
    ssdAudOverTime(tr) = ssd_aud;

    %% fixation
    Screen('TextSize', w, cfg.goTextSize);
    DrawFormattedText(w, '+', 'center', 'center', 255);
    Screen('Flip', w);
    WaitSecs(fixLag(tr));

    %% GO
    Screen('TextSize', w, cfg.goTextSize);
    goStr = num2str(goInstr(tr));
    DrawFormattedText(w, goStr, 'center', 'center', 255);
    goTime = Screen('Flip', w);
    goOn(tr) = goTime;

    %% determine SSD for this trial (if switch)
    if isSwitch(tr)
        if switchType(tr) == SWITCH_VIS
            ssd = ssd_vis;
        else
            ssd = ssd_aud;
        end
        ssdUsed(tr) = ssd;
    else
        ssd = NaN;
    end

    %% response loop
    responded = false;
    switchDelivered = false;

    if isSwitch(tr) && switchType(tr) == SWITCH_AUD
        PsychPortAudio('FillBuffer', pahandle, switchTone); % pre-load
    end

    tEnd = goTime + cfg.respWindow;

    while GetSecs < tEnd

        now = GetSecs;

        % deliver SWITCH cue at goTime + SSD
        if isSwitch(tr) && ~switchDelivered && (now >= goTime + ssd)

            if switchType(tr) == SWITCH_VIS

                Screen('TextSize', w, cfg.switchTextSize);
                % Choose arrow direction to indicate "switch" (not mapping to left/right here)
                % You can replace this with an image later.
                DrawFormattedText(w, '>>>', 'center', 'center', [0 255 0]); % green right arrow →
                switchOn(tr) = Screen('Flip', w);

                % restore GO size
                Screen('TextSize', w, cfg.goTextSize);

            else
                PsychPortAudio('FillBuffer', pahandle, switchTone);
                switchOn(tr) = PsychPortAudio('Start', pahandle, 1, 0, 1);
            end

            switchDelivered = true;
        end

        % check keyboard
        [keyIsDown, keyTime, keyCode] = KbCheck;

        if keyIsDown
            if keyCode(escapeKey)
                error('Experiment aborted');
            end

            if keyCode(key1) || keyCode(key2)
                responded = true;

                rt(tr) = keyTime - goTime;

                if keyCode(key1)
                    resp(tr) = 1;
                else
                    resp(tr) = 2;
                end

                break
            end
        end
    end

    %% score correctness
    if responded
        wasCorrect(tr) = (resp(tr) == correctResp(tr));
    else
        wasCorrect(tr) = 0;
    end

    %% update ladders (independent; ONLY updates ladder for that switch modality)
    if isSwitch(tr)

        switchSuccess(tr) = wasCorrect(tr) == 1;

        if switchType(tr) == SWITCH_VIS
            if switchSuccess(tr)
                ssd_vis = min(cfg.ssdMax, ssd_vis + cfg.ssdStep); % success -> later switch cue
            else
                ssd_vis = max(cfg.ssdMin, ssd_vis - cfg.ssdStep); % fail -> earlier switch cue
            end
        else
            if switchSuccess(tr)
                ssd_aud = min(cfg.ssdMax, ssd_aud + cfg.ssdStep);
            else
                ssd_aud = max(cfg.ssdMin, ssd_aud - cfg.ssdStep);
            end
        end
    end

    %% inter trial
    Screen('Flip', w);
    WaitSecs(cfg.iti);

    trialEndT(tr) = GetSecs;
end

%% timing summary
expEnd = GetSecs;
expElapsed = expEnd - expStart;

trialDur = trialEndT - trialStartT;
avgTrialDur = mean(trialDur, 'omitnan');

%% cleanup
PsychPortAudio('Close', pahandle);
sca;
ShowCursor;
ListenChar(0);

%% print summary
fprintf('\n===== GO-SWITCH SUMMARY =====\n');
fprintf('Elapsed time (s): %.3f\n', expElapsed);
fprintf('Number of trials: %d\n', cfg.ntrials);
fprintf('Avg duration/trial (s): %.3f\n', avgTrialDur);
fprintf('Switch trials: %d (%.1f%%)\n', sum(isSwitch), 100*mean(isSwitch));
fprintf('Overall accuracy: %.1f%%\n', 100*mean(wasCorrect, 'omitnan'));
if any(isSwitch)
    fprintf('Switch success rate: %.1f%%\n', 100*mean(switchSuccess(isSwitch), 'omitnan'));
end
fprintf('Final SSD (visual): %.0f ms\n', 1000*ssd_vis);
fprintf('Final SSD (auditory): %.0f ms\n', 1000*ssd_aud);
fprintf('=============================\n\n');

%% package outputs for easy inspection / saving
out = struct();
out.cfg = cfg;

out.isSwitch = isSwitch;
out.switchType = switchType;
out.goInstr = goInstr;
out.correctResp = correctResp;

out.goOn = goOn;
out.switchOn = switchOn;
out.rt = rt;
out.resp = resp;
out.wasCorrect = wasCorrect;
out.switchSuccess = switchSuccess;
out.ssdUsed = ssdUsed;

out.ssdVisOverTime = ssdVisOverTime;
out.ssdAudOverTime = ssdAudOverTime;

out.expElapsed = expElapsed;
out.trialDur = trialDur;
out.avgTrialDur = avgTrialDur;

fprintf('Visual switch trials: %d | Auditory switch trials: %d\n', ...
    sum(isSwitch & switchType==SWITCH_VIS), sum(isSwitch & switchType==SWITCH_AUD));

%% visualization
figure('Color','w','Name','SSD ladders over time');
plot(1:cfg.ntrials, 1000*out.ssdVisOverTime, '-o'); hold on;
plot(1:cfg.ntrials, 1000*out.ssdAudOverTime, '-o');
xlabel('Trial'); ylabel('SSD (ms)');
legend({'Visual ladder (snapshot each trial)','Auditory ladder (snapshot each trial)'}, 'Location','best');
title('Independent SSD ladders over time');

figure('Color','w','Name','RT distribution');
histogram(out.rt, 25);
xlabel('RT (s)'); ylabel('Count'); title('RTs (final response)');

figure('Color','w','Name','Accuracy');
bar([mean(out.wasCorrect(~out.isSwitch),'omitnan'), mean(out.switchSuccess(out.isSwitch),'omitnan')]);
set(gca,'XTickLabel',{'No-switch','Switch'});
ylabel('Proportion correct');
title('Accuracy');

% stop success by SSD
figure('Color','w'); tiledlayout(1,2)

    % visual
    nexttile
    histogram(out.ssdUsed(out.isSwitch & out.switchType == 1 & out.switchSuccess == 1),'binwidth',0.1)
    hold on; histogram(out.ssdUsed(out.isSwitch & out.switchType == 1 & out.switchSuccess == 0),'binwidth',0.1)
    xlim([0 1]); ylim([0 5]); xlabel('latency'); ylabel('count'); title('visual')
    legend({'success','fail'})
    
    % auditory
    nexttile
    histogram(out.ssdUsed(out.isSwitch & out.switchType == 2 & out.switchSuccess == 1),'binwidth',0.1)
    hold on; histogram(out.ssdUsed(out.isSwitch & out.switchType == 2 & out.switchSuccess == 0),'binwidth',0.1)
    xlim([0 1]); ylim([0 5]); xlabel('latency'); ylabel('count'); title('auditory')
    legend({'success','fail'})
    
    sgtitle('switch success by cue latency')
    

% If you want to save:
% save('goswitch_pilot.mat','out');