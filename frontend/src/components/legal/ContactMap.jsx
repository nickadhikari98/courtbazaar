import React from "react";
import { Marker, Popup } from "react-leaflet";
import MapView, { mapPinIcon } from "@/components/shared/MapView";
import { companyInfo } from "@/config/companyInfo";
import ConfigRequiredBadge from "./ConfigRequiredBadge";

export default function ContactMap({ className = "" }) {
  const { lat, lng } = companyInfo.officeCoordinates;

  return (
    <MapView center={[lat, lng]} zoom={14} aspectClass="aspect-[4/3] sm:aspect-[16/9]" className={className}>
      <Marker position={[lat, lng]} icon={mapPinIcon}>
        <Popup>
          <div className="text-sm">
            <p className="font-display font-bold">CourtBazaar Office</p>
            <p className="text-xs text-muted-foreground mt-1">Okhla, New Delhi</p>
            {companyInfo.officeAddress.needsConfig ? (
              <div className="mt-1.5">
                <ConfigRequiredBadge label="Address pending" />
              </div>
            ) : (
              <p className="text-xs mt-1">{companyInfo.officeAddress.value}</p>
            )}
            <p className="text-xs text-muted-foreground mt-1.5">{companyInfo.businessHours.value}</p>
          </div>
        </Popup>
      </Marker>
    </MapView>
  );
}
