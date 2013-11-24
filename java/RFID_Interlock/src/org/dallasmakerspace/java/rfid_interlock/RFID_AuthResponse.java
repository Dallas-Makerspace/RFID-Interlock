package org.dallasmakerspace.java.rfid_interlock;

/**
 * 
 * @author Mikel
 * 
 * RFID_AuthResponse
 * Object to hold response from server after it is parsed
 *
 */

public class RFID_AuthResponse {
	boolean authorized = false;
	long authTime = 0;
	//String userId = "";
	
	public RFID_AuthResponse(boolean auth, long time) {
		authorized = auth;
		authTime = time;
	}
	
	public boolean isAuthorized() {
		return authorized;
	}
	
	public long getAuthTime() {
		return authTime;
	}
	
	public void setAuthorized(boolean auth) {
		authorized = auth;
	}
	
	public void setAuthTime(long time) {
		authTime = time;
	}
}
