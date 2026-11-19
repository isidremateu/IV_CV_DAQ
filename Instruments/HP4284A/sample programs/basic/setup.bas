1000   !*****************************************************
1010   !* DESCRIPTION:  Agilent 4284A Sample Program
1020   !*
1030   !* AUTHOR:       Agilent Technologies Japan, Ltd.
1040   !* CREATED:       1/16/2003
1050   !* PROGRAM NAME: setup.bas
1060   !* REVISION:     A.01.00
1070   !*
1080   !*   (c) Copyright 2003 Agilent Technologies,
1090   !*              All rights reserved.
1100   !*
1110   !*
1120   !*  Customer shall have the personal, non-
1130   !* transferable rights to use, copy or modify
1140   !* this SAMPLE PROGRAM for Customer's internal
1150   !* operations. Customer shall use the SAMPLE
1160   !* PROGRAM solely and exclusively for its own
1170   !* purpose and shall not license, lease, market
1180   !* or distribute the SAMPLE PROGRAM or
1190   !* modification or any part thereof.
1200   !*
1210   !*  Agilent Technologies shall not be liable for
1220   !* the quality, performance or behavior of the
1230   !* SAMPLE PROGRAM. Agilent Technologies especially
1240   !* disclaims that the operation of the SAMPLE
1250   !* PROGRAM shall be uninterrupted or error free.
1260   !* This SAMPLE PROGRAM is provided AS IS.
1270   !*
1280   !*  AGILENT TECHNOLOGIES DISCLAIMS THE IMPLIED
1290   !* WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
1300   !* A PARTICULAR PURPOSE.
1310   !*
1320   !*  Agilent Technologies shall not be liable for
1330   !* any infringement of any patent, trademark,
1340   !* copyright or other proprietary rights by the
1350   !* SAMPLE PROGRAM or its use. Agilent Technologies
1360   !* does not warrant that the SAMPLE PROGRAM is
1370   !* free from infringements or such rights of third
1380   !* parties. However, Agilent Technologies will not
1390   !* knowingly infringe or deliver a software that
1400   !* infringes the patent, trademark, copyright or
1410   !* other proprietary right of a third party.
1420   !*
1430   !*****************************************************
1440   !
1450  ASSIGN @Meter TO 717
1460  REMOTE @Meter
1470  OUTPUT @Meter;"DISP:PAGE MSET"
1480  OUTPUT @Meter;"DISP:LINE ""Control Example"""
1490  OUTPUT @Meter;"FUNC:IMP ZTD"
1500  OUTPUT @Meter;"FREQ 1MHZ"
1510  OUTPUT @Meter;"VOLT 1V"
1520  OUTPUT @Meter;"TRIG:SOUR BUS"
1530  OUTPUT @Meter;"AMPL:ALC ON"
1540  OUTPUT @Meter;"OUTP:HPOW ON"
1550  OUTPUT @Meter;"OUTP:DC:ISOL ON"
1560  OUTPUT @Meter;"FUNC:IMP:RANG 10KOHM"
1570  OUTPUT @Meter;"BIAS:VOLT 5"
1580  OUTPUT @Meter;"APER LONG,4"
1590  OUTPUT @Meter;"FUNC:SMON:VAC ON"
1600  OUTPUT @Meter;"FUNC:SMON:IAC ON"
1610  OUTPUT @Meter;"TRIG:DEL 5"
1620  OUTPUT @Meter;"FUNC:DEV1:MODE ABS"
1630  OUTPUT @Meter;"FUNC:DEV2:MODE ABS"
1640  OUTPUT @Meter;"FUNC:DEV1:REF 10000"
1650  OUTPUT @Meter;"FUNC:DEV2:REF 1"
1660  END
