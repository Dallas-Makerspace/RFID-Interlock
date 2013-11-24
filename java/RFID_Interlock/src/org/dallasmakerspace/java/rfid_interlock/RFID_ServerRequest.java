package org.dallasmakerspace.java.rfid_interlock;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.net.MalformedURLException;
import java.net.URL;
import java.net.URLConnection;

/**
 * 
 * @author Mikel
 * 
 * RFID_ServerRequest
 * Makes request to server for authorization status
 *
 */

public class RFID_ServerRequest {
	private String urlStr;
	private RFID_AuthResponse ar;
	
	public RFID_ServerRequest(String url) {
		this.urlStr = url;
	}
	
	public void setUrl(String url) {
		urlStr = url;
	}
	
	//returns true if it got a response, and sets static var RFID_Interlock to response object
	public boolean makeRequest() {
		try {
			URL url = new URL(urlStr);
			URLConnection con = url.openConnection();
			
			BufferedReader br = new BufferedReader(new InputStreamReader(con.getInputStream()));
			
			String in = "";
			while (br.ready()) {
				in += "\n" + br.readLine();
			}
			br.close();
			
			//returns true if it got a response
			if (!in.equals("")) {
				ar = handleResponse(in);
				return true;
			}
			else {
				return false;
			}
			
		}
		catch (MalformedURLException e) {
			System.out.println("Error in URL: " + e);
			return false;
		}
		catch (IOException e) {
			System.out.println("Error opening URL: " + e);
			return false;
		}
	}
	
	public RFID_AuthResponse getAR() {
		return ar;
	}
	
	//parses response from server
	private RFID_AuthResponse handleResponse(String str) {
		if (RFID_Settings.debug) System.out.print("Response Received: " + str);
		boolean auth = false;
		long time = 0;
		String authStr = "\"authorized\":true";
		String timeStr = "\"timeout\":";
		
		if (str.contains(authStr)) auth = true;
		int in = str.indexOf(timeStr);
		if (in > -1) {
			in += timeStr.length();
			String s = str.substring(in, str.length() - 1);
			time = Long.parseLong(s);
		} 
		 
		return new RFID_AuthResponse(auth, time);
	}
}
