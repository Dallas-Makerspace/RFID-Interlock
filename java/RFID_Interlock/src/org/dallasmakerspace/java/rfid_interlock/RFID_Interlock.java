package org.dallasmakerspace.java.rfid_interlock;

import java.io.*;

/**
 * 
 * @author Mikel
 *
 * RFID_Interlock
 * Main class for RFID_Interlock app. Currently runs from console.
 * 
 * TODO: Add reading rfid from serial if needed later
 */

public class RFID_Interlock
{
	private boolean run = true;
    private BufferedReader br;
	private String input = "";
		
	private RFID_AuthResponse ar;
	private RFID_Timer timer;
	
	private static BBB_DIGITAL_GPIO mPin;

	@SuppressWarnings("unused")
	public static void main(String args[]) {
		RFID_Settings.loadSettings();
		
		if (RFID_Settings.enableBBHW) mPin = new BBB_DIGITAL_GPIO(true, RFID_Settings.machinePin, RFID_Settings.debug);
		
		RFID_Interlock rfid_app = new RFID_Interlock(true);
    }
	
	public RFID_Interlock(boolean consoleMode) {
		if (consoleMode) {
			System.out.println("RFID Interlock Console Mode");
			consoleReader();
		}
		else {
			System.out.println("RFID Interlock");
		}
	}
	
	private void consoleReader() {
		try {
			br = new BufferedReader(new InputStreamReader(System.in));
			
			//continuous input loop
			while (run) {
				System.out.print("Enter ID: ");
				input = br.readLine();
				//System.out.println("You Entered: " + input);
				
				if (input.equalsIgnoreCase("quit") || input.equalsIgnoreCase("exit")) {
					run = false;
					System.out.println("Exiting");
					return;
				}
				else if (isValidId(input)) {
					String builtUrl = buildURL(input);
					if (RFID_Settings.debug) System.out.println("URL: " + builtUrl);
					
					RFID_ServerRequest sr = new RFID_ServerRequest(builtUrl);
					System.out.println("Making Request");
					
					if (sr.makeRequest()) {
						ar = sr.getAR();
						if (RFID_Settings.debug) System.out.println("Request Response for " + input + ": Authorized: " + ar.isAuthorized() + " Time: " + ar.getAuthTime());
						if (ar.authorized && ar.getAuthTime() > 0) {
							System.out.println("User is Authorized for " + ar.getAuthTime());
							enableMachine();
						}
						else System.out.println("Denied");
					}
				}
				else {
					System.out.println("Invalid Input");
				}
			}
		}
		catch (Exception e) {
			System.out.println("Error: " + e);
		}
	}
	
	private String buildURL(String id) {
		String wsUrl = RFID_Settings.apiUrl + RFID_Settings.badgeVar + id;
		if (RFID_Settings.toolId != null) wsUrl += RFID_Settings.toolVar + RFID_Settings.toolId;
		return wsUrl;
	}
	
	private boolean isValidId(String str) {
		if (str.length() < 7 || str.length() > 10) return false; 
		return str.matches("-?\\d+(\\.\\d+)?");
	}
	
	private void enableMachine() {
		System.out.println("On");
		if (RFID_Settings.enableBBHW) mPin.enablePin();
		
		if (timer != null && timer.isAlive()) timer.stopTimer();
		timer = new RFID_Timer(ar.getAuthTime() * 1000);
		timer.start();
	}
	
	public static void disableMachine() {
		System.out.println("\nOff");
		if (RFID_Settings.enableBBHW) mPin.disablePin();
	}
}

