import React from "react";
import { motion } from "framer-motion";
import PricingCard from "./PricingCard";
import BulkPricingOffer from "./pricing/BulkPricingOffer";
import { packages } from "@/lib/pricingData";

const gridVariants = {
  hidden: {},
  visible: {
    transition: { staggerChildren: 0.15 },
  },
};

const cardVariants = {
  hidden: { opacity: 0, y: 28, scale: 0.96 },
  visible: {
    opacity: 1,
    y: 0,
    scale: 1,
    transition: { duration: 0.6, ease: [0.22, 1, 0.36, 1] },
  },
};

export default function PricingSection() {
  return (
    <section id="pricing" className="landing-section bg-slate-50">
      <div className="landing-container">
        <div className="landing-section-header">
          <h2 className="landing-section-title">Choose a Plan That Suits You</h2>
          <p className="landing-section-subtitle">
            Flexible plans for individuals, advocates, law firms and litigation teams.
          </p>
        </div>

        <motion.div
          className="grid grid-cols-1 md:grid-cols-3 gap-6 max-w-5xl mx-auto items-stretch"
          variants={gridVariants}
          initial="hidden"
          whileInView="visible"
          viewport={{ once: false, amount: 0.2 }}
        >
          {packages.map((pkg) => (
            <motion.div key={pkg.name} className="h-full grid" variants={cardVariants}>
              <PricingCard {...pkg} />
            </motion.div>
          ))}
        </motion.div>

        <div className="mt-8">
          <BulkPricingOffer
            title="More than 1000 pages?"
            subtitle="Get special bulk pricing for law firms, senior advocates, chambers and litigation teams."
          />
        </div>
      </div>
    </section>
  );
}
