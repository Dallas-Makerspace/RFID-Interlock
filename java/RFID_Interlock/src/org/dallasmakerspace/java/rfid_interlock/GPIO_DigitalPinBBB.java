package org.dallasmakerspace.java.rfid_interlock;

import java.io.FileInputStream;
import java.io.FileNotFoundException;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.PrintWriter;

/**
 * 
 * @author Mikel
 *
 * Class for methods to handle hardware GPIO for the BeagleBoneBlack
 */

public class GPIO_DigitalPinBBB extends GPIO_DigitalPin {
	private String pin = "";
	private boolean output = true;
	private boolean debug = false;
	private boolean enabled = false;
	
	final public static int HIGH = 1;
	final public static int LOW  = 0;
	
	FileOutputStream out;
	PrintWriter pw;
	
	FileInputStream in;
	
	public GPIO_DigitalPinBBB(boolean outputPin, String pin, boolean debug) {
		this.output = outputPin;
		this.pin = pin;
		this.debug = debug;
		
		if (debug) System.out.println("Setup Pin: " + pin);
		
		//create export for pin
		try {
			//create pin for io
			if (debug) System.out.println("Creating pin " + pin + " for io");
			out = new FileOutputStream("/sys/class/gpio/export");
			PrintWriter pw = new PrintWriter(out);
			pw.print(pin);
			pw.close();
		}
		catch (FileNotFoundException e) {
			System.out.println("File Not Found, Are you sure this is a BBB? " + e);
			try {
				out.close();
			} catch (IOException e1) {
				System.out.println("Error closing stream after error: " + e);
			}
			return;
		}
				
		if (outputPin) {
			try {
				if (debug) System.out.println("Enabling pin " + pin + " for output");
				//set pin for output
				out = new FileOutputStream("/sys/class/gpio/gpio" + pin + "/direction");
				pw = new PrintWriter(out);
				pw.print("out");
				pw.close();
				out.close();
				
				//setup pw for io
				out = new FileOutputStream("/sys/class/gpio/gpio" + pin + "/value");
				pw = new PrintWriter(out);
				
				enabled = true;
			}
			catch (FileNotFoundException e) {
				System.out.println("File Not Found, Are you sure this is a BBB? " + e);
			}
			catch (IOException e) {
				System.out.println("IOException: " + e);
			}
		}
		else {
			try {
				//set pin for input
				if (debug) System.out.println("Enabling pin " + pin + " for input");
				out = new FileOutputStream("/sys/class/gpio/gpio" + pin + "/direction");
				pw = new PrintWriter(out);
				pw.print("in");
				pw.close();
				out.close();
				
				//setup pw for io
				in = new FileInputStream("/sys/class/gpio/gpio" + pin + "/value");
				
				enabled = true;
			}
			catch (FileNotFoundException e) {
				System.out.println("File Not Found, Are you sure this is a BBB? " + e);
			}
			catch (IOException e) {
				System.out.println("IOException: " + e);
			}
		}
	}
	
	public void setDebug(boolean d) {
		debug = d;
	}
	
	@Override
	public void enablePin() {
		if (enabled) {
			if (debug) System.out.println("Enable: " + pin);
			FileOutputStream out = null;
			try {
				out = new FileOutputStream("/sys/class/gpio/gpio" + pin + "/value");
				PrintWriter pw = new PrintWriter(out);
				pw = new PrintWriter(out);
				pw.print(HIGH);
				pw.close();
			} catch (Exception e) {
			    throw new RuntimeException(e);
			} finally {
			    try {
					out.close();
				} catch (IOException e) {
					e.printStackTrace();
				}
			}
		}
	}
	
	@Override
	public void disablePin() {
		if (enabled) {
			if (debug) System.out.println("Disable: " + pin);
			FileOutputStream out = null;
			try {
				out = new FileOutputStream("/sys/class/gpio/gpio" + pin + "/value");
				PrintWriter pw = new PrintWriter(out);
				pw = new PrintWriter(out);
				pw.print(LOW);
				pw.close();
			} catch (Exception e) {
			    throw new RuntimeException(e);
			} finally {
			    try {
					out.close();
				} catch (IOException e) {
					e.printStackTrace();
				}
			}
		}
	}
	
	@Override
	public void close() {
		try {
			pw.close();
			out.close();
		}
		catch (IOException e) {
			System.out.println("Error closing gpio stream: " + e);
		}
	}
	
	//TODO test this
	@Override
	public int getValue() {
		int val = 0;
		if (output) return val;
		else {
			try {
				in = null;
				in = new FileInputStream("/sys/class/gpio/gpio" + pin + "/value");
				val = in.read() - 48; //48 is 0 Off for some reason
				in.close();
			} catch (IOException e) {
				System.out.println("Error reading input value: " + e);
			}
		}
		return val;
	}
}
