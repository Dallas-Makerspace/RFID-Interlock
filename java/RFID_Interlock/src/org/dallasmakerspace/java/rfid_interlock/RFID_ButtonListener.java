package org.dallasmakerspace.java.rfid_interlock;

public class RFID_ButtonListener extends Thread{
	String buttonPin = "";
	GPIO_DigitalPin pin;
	
	private boolean run = false;
	private boolean listening = false;
	private long updateFrequency = 10;
	
	public RFID_ButtonListener(String bPin, long updateFreq) {
		buttonPin = bPin;
		updateFrequency = updateFreq;
		
		if (RFID_Settings.enableBBHW) pin = new GPIO_DigitalPinBBB(false, RFID_Settings.buttonPin, RFID_Settings.debug);
		else if (RFID_Settings.enableRPiHW) pin = new GPIO_DigitalPinRpi(false, RFID_Settings.buttonPin, RFID_Settings.debug);
		
		this.start();
	}
	
	public void run() {
		int inVal = 0;
		run = true;
		while (run) {
			try {
				if (listening) {
					inVal = pin.getValue();
					if (RFID_Settings.debug && inVal > 0) System.out.println("Button Status: " +inVal);
					
					if (inVal > 0) {
						System.out.println("Stop button pressed");
						RFID_Interlock.disableMachine();
						listening = false;
					}
				}
				Thread.sleep(updateFrequency);
			}
			catch (InterruptedException e) {
				System.out.println("Error sleeping ButtonLister " + buttonPin + ": " + e);
			}
		}
	}
	
	public void quitListening() {
		listening = false;
		//this.interrupt();
	}
	
	public void startListening() {
		listening = true;
	}
	
	public boolean isRunning() {
		return run;
	}
}
