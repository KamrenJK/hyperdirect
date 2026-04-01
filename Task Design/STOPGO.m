% ==============================================================
% STOP SIGNAL TASK (minimal working demo)
% auditory vs visual stop cues with independent SSD ladders
%
% Ladder rule (as requested):
%   SUCCESSFUL stop (no response) -> SSD increases by +step (harder next time)
%   FAILED stop (response)        -> SSD decreases by -step (easier next time)
%
% Tracks SSD over time (per trial) for BOTH ladders and ensures independence.
% Prints elapsed time, #trials, avg duration/trial, and shows SSD evolution.
% ==============================================================

clear; clc; close all

KbName('UnifyKeyNames');

%% experiment parameters
cfg.ntrials    = 100;
cfg.stopFrac   = 0.36;     % for pilots; typical is 0.25

cfg.fixMin     = 1.5;
cfg.fixMax     = 2.0;

cfg.respWindow = 1.5;

cfg.ssdStart   = 0.300;
cfg.ssdStep    = 0.050;

cfg.ssdMin     = 0.055;
cfg.ssdMax     = 1.000;

% text sizes (kept constant)
cfg.goTextSize   = 120;    % fixation and GO digit
cfg.stopTextSize = 150;    % STOP X

%% keys
key1 = KbName('1!');
key2 = KbName('2@');
escapeKey = KbName('ESCAPE');

%% trial schedule
isStop = rand(cfg.ntrials,1) < cfg.stopFrac;

STOP_VIS = 1;
STOP_AUD = 2;

stopType = nan(cfg.ntrials,1);
stopIdx  = find(isStop);
nStop    = length(stopIdx);

% Balance auditory vs visual within stop trials
tmp = [repmat(STOP_VIS, ceil(nStop/2), 1); repmat(STOP_AUD, floor(nStop/2), 1)];
tmp = tmp(randperm(length(tmp)));
stopType(stopIdx) = tmp(1:nStop);

goInstr = randi([1 2], cfg.ntrials, 1);
fixLag  = cfg.fixMin + rand(cfg.ntrials,1)*(cfg.fixMax - cfg.fixMin);

%% ladders (independent)
ssd_vis = cfg.ssdStart;
ssd_aud = cfg.ssdStart;

%% audio stop cue
InitializePsychSound(1);
fs = 44100;

toneDur = 0.15;
toneAmp = 0.75;

t = 0:1/fs:toneDur;

tone = ...
    sin(2*pi*900*t) + ...
    sin(2*pi*1370*t) + ...
    sin(2*pi*2130*t);

tone = tone / max(abs(tone));   % normalize
tone = tone * toneAmp;

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
    'Press 1 for "1"\nPress 2 for "2"\n\nStop when you see X or hear a tone\n\nPress any key to start', ...
    'center','center',255);
Screen('Flip', w);
KbStrokeWait;

%% allocate data
rt          = nan(cfg.ntrials,1);
resp        = nan(cfg.ntrials,1);
stopSuccess = nan(cfg.ntrials,1);

goOn        = nan(cfg.ntrials,1);
stopOn      = nan(cfg.ntrials,1);   % onset timestamp (Flip time or audio start time)
ssdUsed     = nan(cfg.ntrials,1);   % SSD used on that trial (stop trials only)

% SSD ladder values *over time* (snapshot each trial)
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

    % snapshot current ladder values so you can plot evolution
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

    %% determine SSD for this trial (if stop)
    if isStop(tr)
        if stopType(tr) == STOP_VIS
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
    stopDelivered = false;

    if isStop(tr) && stopType(tr) == STOP_AUD
        PsychPortAudio('FillBuffer', pahandle, tone); % pre-load
    end

    tEnd = goTime + cfg.respWindow;

    while GetSecs < tEnd

        now = GetSecs;

        % deliver stop cue at goTime + SSD (best-effort; loop jitter exists)
        if isStop(tr) && ~stopDelivered && (now >= goTime + ssd)

            if stopType(tr) == STOP_VIS
                Screen('TextSize', w, cfg.stopTextSize);
                DrawFormattedText(w, 'X', 'center', 'center', [255 0 0]);
                stopOn(tr) = Screen('Flip', w);

                % restore GO size for subsequent draws
                Screen('TextSize', w, cfg.goTextSize);

            else
                PsychPortAudio('FillBuffer', pahandle, tone);
                stopOn(tr) = PsychPortAudio('Start', pahandle, 1, 0, 1);
            end

            stopDelivered = true;
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

    %% update ladders (independent; ONLY updates the ladder for that stop modality)
    if isStop(tr)

        stopSuccess(tr) = ~responded;

        if stopType(tr) == STOP_VIS
            if stopSuccess(tr)
                ssd_vis = min(cfg.ssdMax, ssd_vis + cfg.ssdStep); % success -> later stop
            else
                ssd_vis = max(cfg.ssdMin, ssd_vis - cfg.ssdStep); % fail -> earlier stop
            end
        else
            if stopSuccess(tr)
                ssd_aud = min(cfg.ssdMax, ssd_aud + cfg.ssdStep);
            else
                ssd_aud = max(cfg.ssdMin, ssd_aud - cfg.ssdStep);
            end
        end
    end

    %% inter trial
    Screen('Flip', w);
    WaitSecs(0.3);

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
fprintf('\n===== STOPGO SUMMARY =====\n');
fprintf('Elapsed time (s): %.3f\n', expElapsed);
fprintf('Number of trials: %d\n', cfg.ntrials);
fprintf('Avg duration/trial (s): %.3f\n', avgTrialDur);
fprintf('Stop trials: %d (%.1f%%)\n', sum(isStop), 100*mean(isStop));
if any(isStop)
    fprintf('Stop success rate: %.1f%%\n', 100*mean(stopSuccess(isStop), 'omitnan'));
end
fprintf('Final SSD (visual): %.0f ms\n', 1000*ssd_vis);
fprintf('Final SSD (auditory): %.0f ms\n', 1000*ssd_aud);
fprintf('==========================\n\n');

%% package outputs for easy inspection / saving
out = struct();
out.cfg = cfg;
out.isStop = isStop;
out.stopType = stopType;
out.goInstr = goInstr;

out.goOn = goOn;
out.stopOn = stopOn;
out.rt = rt;
out.resp = resp;
out.stopSuccess = stopSuccess;
out.ssdUsed = ssdUsed;

out.ssdVisOverTime = ssdVisOverTime;
out.ssdAudOverTime = ssdAudOverTime;

out.expElapsed = expElapsed;
out.trialDur = trialDur;
out.avgTrialDur = avgTrialDur;

% Show how SSD evolved on stop trials only (for quick debugging)
visStopTrials = isStop & stopType==STOP_VIS;
audStopTrials = isStop & stopType==STOP_AUD;

fprintf('Visual stop trials: %d | Auditory stop trials: %d\n', sum(visStopTrials), sum(audStopTrials));

%% data visualization

% plot SSD ladders
figure('Color','w','Name','SSD ladders over time');
plot(1:cfg.ntrials, 1000*out.ssdVisOverTime, '-o'); hold on;
plot(1:cfg.ntrials, 1000*out.ssdAudOverTime, '-o');
xlabel('Trial'); ylabel('SSD (ms)');
legend({'Visual ladder (snapshot each trial)','Auditory ladder (snapshot each trial)'}, 'Location','best');
title('Independent SSD ladders over time');

% plot reaction time
figure('Color','w');
histogram(out.rt(out.goInstr==1),'binwidth',0.1)
hold on; histogram(out.rt(out.goInstr==2),'binwidth',0.1)
legend({'1','2'})
xlabel('RT (s)'); ylabel('count')
title('RT by go cue');

% plot 
figure('Color','w');
histogram(out.trialDur(out.isStop),'BinWidth',0.1)
hold on; histogram(out.trialDur(~out.isStop),'BinWidth',0.1)
legend({'stop','non-stop'})
xlabel('trial dur (s)'); ylabel('count')
title('trial dur by stop vs non-stop');

% stop success by SSD
figure('Color','w'); tiledlayout(1,2)

    % visual
    nexttile
    histogram(out.ssdUsed(out.isStop & out.stopType == 1 & out.stopSuccess == 1),'binwidth',0.1)
    hold on; histogram(out.ssdUsed(out.isStop & out.stopType == 1 & out.stopSuccess == 0),'binwidth',0.1)
    xlim([0 1]); ylim([0 5]); xlabel('latency'); ylabel('count'); title('visual')
    legend({'success','fail'})
    
    % auditory
    nexttile
    histogram(out.ssdUsed(out.isStop & out.stopType == 2 & out.stopSuccess == 1),'binwidth',0.1)
    hold on; histogram(out.ssdUsed(out.isStop & out.stopType == 2 & out.stopSuccess == 0),'binwidth',0.1)
    xlim([0 1]); ylim([0 5]); xlabel('latency'); ylabel('count'); title('auditory')
    legend({'success','fail'})
    
    sgtitle('movement cancellation success by cue latency')
    
% stop success by cue type
figure('Color','w');
bar(1,sum(out.stopType==1 & out.stopSuccess==1)/(sum(out.stopType==1)))
hold on; bar(2,sum(out.stopType==2 & out.stopSuccess==1)/(sum(out.stopType==2)))
xticks([1 2]); xticklabels({'visual','auditory'}); ylabel('success (%)')
%% save
% save('stopgo_pilot.mat','out');