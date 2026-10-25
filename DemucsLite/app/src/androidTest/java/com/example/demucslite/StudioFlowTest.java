package com.example.demucslite;

import android.os.SystemClock;
import android.view.View;
import android.widget.SeekBar;

import androidx.test.core.app.ActivityScenario;
import androidx.test.ext.junit.runners.AndroidJUnit4;

import org.junit.Test;
import org.junit.runner.RunWith;

import java.util.concurrent.atomic.AtomicBoolean;

import static androidx.test.espresso.Espresso.onView;
import static androidx.test.espresso.action.ViewActions.click;
import static androidx.test.espresso.action.ViewActions.scrollTo;
import static androidx.test.espresso.assertion.ViewAssertions.matches;
import static androidx.test.espresso.matcher.ViewMatchers.*;
import static org.hamcrest.Matchers.allOf;
import static org.junit.Assert.*;

@RunWith(AndroidJUnit4.class)
public class StudioFlowTest {
    @Test public void startOpensUploadWithDisabledSubmitUntilAFileIsSelected() {
        try(ActivityScenario<MainActivity> scenario=ActivityScenario.launch(MainActivity.class)) {
            onView(withId(R.id.btnStart)).perform(scrollTo(),click());
            onView(withId(R.id.uploadZone)).check(matches(isDisplayed()));
            onView(withId(R.id.btnSeparate)).check(matches(org.hamcrest.Matchers.not(isEnabled())));
        }
    }

    @Test public void demoSupportsPlaybackMixRotationAndWavExport() {
        try(ActivityScenario<MainActivity> scenario=ActivityScenario.launch(MainActivity.class)) {
            onView(withId(R.id.btnDemo)).perform(scrollTo(),click());
            AtomicBoolean ready=new AtomicBoolean();
            long deadline=SystemClock.uptimeMillis()+12000;
            while(!ready.get()&&SystemClock.uptimeMillis()<deadline) {
                scenario.onActivity(activity -> ready.set(activity.findViewById(R.id.screenMixer).getVisibility()==View.VISIBLE
                        &&activity.findViewById(R.id.btnPlayAll).isEnabled()));
                SystemClock.sleep(100);
            }
            assertTrue("Demo should prepare four playable stems",ready.get());
            onView(withId(R.id.mixerMeta)).check(matches(withText("DEMO · Âm thanh tổng hợp")));
            scenario.onActivity(activity -> {
                SeekBar volume=activity.findViewById(R.id.trackVocals).findViewById(R.id.stemVolume);
                volume.setProgress(37);
            });
            onView(allOf(withId(R.id.stemPercent),isDescendantOfA(withId(R.id.trackVocals))))
                    .check(matches(withText("37%")));
            onView(allOf(withId(R.id.stemSolo),isDescendantOfA(withId(R.id.trackVocals)))).perform(click());
            onView(withId(R.id.btnPlayAll)).perform(click());
            onView(withId(R.id.btnPlayAll)).check(matches(withContentDescription("Tạm dừng bản phối")));
            scenario.recreate();
            onView(allOf(withId(R.id.stemPercent),isDescendantOfA(withId(R.id.trackVocals))))
                    .check(matches(withText("37%")));
            onView(withId(R.id.btnExport)).perform(scrollTo(),click());
            long savedDeadline=SystemClock.uptimeMillis()+8000;
            AtomicBoolean saved=new AtomicBoolean();
            while(!saved.get()&&SystemClock.uptimeMillis()<savedDeadline) {
                try { onView(withText("Đã lưu 4 track ✨")).check(matches(isDisplayed()));saved.set(true); }
                catch(androidx.test.espresso.NoMatchingViewException|AssertionError ignored) { SystemClock.sleep(100); }
            }
            assertTrue("WAV export should finish",saved.get());
            onView(withText("Xong")).perform(click());
            onView(withId(R.id.navHome)).perform(click());
            scenario.recreate();
            onView(withId(R.id.screenHome)).check(matches(isDisplayed()));
        }
    }
}
