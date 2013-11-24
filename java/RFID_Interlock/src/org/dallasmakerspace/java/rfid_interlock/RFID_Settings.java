package org.dallasmakerspace.java.rfid_interlock;

import java.io.File;
import java.io.FileNotFoundException;
import java.util.Scanner;

/**
 * 
 * @author Mikel
 *
 * Class to load settings from config file and allow access from other classes
 * Defaults below may be overwritten by loadSettings()
 */
public class RFID_Settings {
	public static  String apiUrl = "http://dallasmakerspace.org/makermanager/index.php?r=api/toolValidate";
	public static  String badgeVar = "&badge=";
	public static  String toolVar  = "&tool=";
	public static  String toolId = "1";
	
	public static boolean debug = false;
	public static boolean consoleMode = true;
	
	private static String fileName = "RFID_Settings.cfg";
	
	public static void loadSettings() {
		try {
			Scanner sc = new Scanner(new File(fileName));
			String input = "";
			
			while (sc.hasNext()) input += sc.nextLine() + "\n";
			if (debug) System.out.println(input);
			
			processFile(input);
			sc.close();
		} catch (FileNotFoundException e) {
			System.out.println("Settings File Not Found");
			//e.printStackTrace();
		}
	}
	
	private static void processFile(String str) {
		String line[] = str.split("\n");
		for (int i = 0; i < line.length; i++) {
			
			String sp[] = line[i].trim().split(":");
			
			if (sp.length < 2) continue;
			sp[0] = sp[0].trim();
			
			String val = sp[1].trim();
			
			if (sp[0].contains("Url")) {
				val = sp[1];
				if (sp.length >= 2) {
					for (int j = 2; j < sp.length; j++)
						val += ":" + sp[j];
				}
				apiUrl = val.trim();
			}
			else if (sp[0].contains("badgeVar")) badgeVar = val;
			else if (sp[0].contains("toolVar"))  toolVar  = val;
			else if (sp[0].contains("toolId"))   toolId   = val;
			else if (sp[0].contains("debug"))    debug = sp[1].trim().contains("true");
			else if (sp[0].contains("consoleMode")) consoleMode = sp[1].trim().contains("true");
			
			if (debug) System.out.println("var: " + sp[0] + " val: " + val);
		}
	}
}
