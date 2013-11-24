package org.dallasmakerspace.java.rfid_interlock;

/**
 * 
 * @author Mikel
 *
 * RFID_Timer
 * Timer object, checks to see if device is on and starts countdown once it is off.
 * Timer resets if device is turned on.
 * Calls static method RFID_Interlock.disableMachine() if the timer runs down.
 * Call stopTimer() method to stop timer and close thread 
 */

public class RFID_Timer extends Thread {
	long timerTime = 0;
	long startTime = 0;
	long runTime   = 0;
	long delayAmt = 10;
	boolean run = true;
	
	RFID_CurrentDetector cd;
	
	public RFID_Timer(long t) {
		timerTime = t;
		cd = new RFID_CurrentDetector();
	}
	
	public void setTimer(long t) {
		timerTime = t;
	}
	
	public void run() {
		while (run) {
			startTime = System.currentTimeMillis();
			while (run && !cd.deviceOn() && runTime < timerTime) {
				runTime = System.currentTimeMillis() - startTime;
				try {
					Thread.sleep(delayAmt);
				} catch (InterruptedException e) {
					System.out.println("Error Sleeping Thread: " + e);
				}
			}
			if (!cd.deviceOn() && runTime >= timerTime) {
				run = false;
				RFID_Interlock.disableMachine();
				return;
			}
		}
	}
	
	public void stopTimer() {
		run = false;
	}
}
