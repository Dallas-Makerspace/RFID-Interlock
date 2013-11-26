package org.dallasmakerspace.java.rfid_interlock;

/**
 * 
 * @author Mikel
 *
 */

public abstract class GPIO_DigitalPin {
	abstract void enablePin();
	abstract void disablePin();
	abstract void close();
	abstract int getValue();
}
