# -*- coding: utf-8 -*-
# Vendored from mapbiomas-pipeline @ c50594f (deforestation/deforestation_secondary_vegetation.py), unchanged.
import ee

class DeforestationSecondaryVegetation:
    """
    A class to apply rule-based logic for detecting deforestation and secondary vegetation transitions
    using a classification image and a defined sequence of years, following MapBiomas classification logic.

    Parameters:
    - image: ee.Image with bands representing land cover classification per year
    - years: list of int, ordered sequence of years corresponding to classification bands

    Notes:
    - All logical operations use Earth Engine's native methods like `.And()` instead of Python bitwise operators (`&`).
    - Designed to be modular and extendable for additional rule types or kernel sizes.
    """

    def __init__(self, image, years):
        self.image = image
        self.years = years

    def apply_rule_kernel_4(self, rule, years):
        """
        Apply a 4-year kernel rule to the classification image using map().

        Parameters:
        - rule: list of three elements [kernel_bef, kernel_aft, min_start]
            - kernel_bef: list of 4 class IDs that must match the input (before state)
            - kernel_aft: list of 4 class IDs to write on match (after state)
            - min_start: int, minimum index in years from which the rule may be applied.
                         Must be set explicitly for every rule:
                         - 0: rule is safe from the first year of the series (no class 3 or 5 written at t2)
                         - 1: rule assigns class 3 or 5 at t2; requires confirmed prior state before t1
                         Omitting min_start is not allowed — raises ValueError to prevent silent errors.
        - years: list of int, years to apply the rule to
        """
        if len(rule) < 3:
            raise ValueError(
                f"Rule is missing min_start (3rd element): {rule}. "
                "Set min_start=0 explicitly if the rule is safe from the first year of the series."
            )

        kernel_bef = rule[0]
        kernel_aft = rule[1]
        min_start  = ee.Number(rule[2])
        years_list = ee.List(years)

        def apply_kernel_4(i, image):
            i = ee.Number(i)
            img = ee.Image(image)

            y1 = years_list.get(i)
            y2 = years_list.get(i.add(1))
            y3 = years_list.get(i.add(2))
            y4 = years_list.get(i.add(3))

            b1 = ee.String('classification_').cat(ee.String(y1))
            b2 = ee.String('classification_').cat(ee.String(y2))
            b3 = ee.String('classification_').cat(ee.String(y3))
            b4 = ee.String('classification_').cat(ee.String(y4))

            t1 = img.select(b1)
            t2 = img.select(b2)
            t3 = img.select(b3)
            t4 = img.select(b4)

            mask = (
                t1.eq(kernel_bef[0])
                .And(t2.eq(kernel_bef[1]))
                .And(t3.eq(kernel_bef[2]))
                .And(t4.eq(kernel_bef[3]))
                .And(i.gte(min_start))  # blocks windows before min index
            )

            t1 = t1.where(mask, kernel_aft[0]).rename(b1)
            t2 = t2.where(mask, kernel_aft[1]).rename(b2)
            t3 = t3.where(mask, kernel_aft[2]).rename(b3)
            t4 = t4.where(mask, kernel_aft[3]).rename(b4)

            return img.addBands([t1, t2, t3, t4], overwrite=True)

        # Iterate over all valid 4-year windows
        self.image = ee.List.sequence(0, len(years) - 4).iterate(apply_kernel_4, self.image)


    def apply_rule_kernel_6(self, rule, years):
        """
        Apply a 6-year kernel rule to the classification image using iterate().

        Intended for anchored end-of-series rules (secondary vegetation): pass a
        `years` list of exactly 6 elements (e.g. YEARS[-6:]) so that only the
        single window [n-5 .. n] is evaluated.

        Parameters:
        - rule: list of three elements [kernel_bef, kernel_aft, min_start]
            - kernel_bef: list of 6 class IDs that must match the input (before state)
            - kernel_aft: list of 6 class IDs to write on match (after state)
            - min_start: int, minimum index in years from which the rule may be applied.
                         Must be set explicitly for every rule:
                         - 0: rule is safe from the first year of the series (no class 3 or 5 written at t2)
                         - 1: rule assigns class 3 or 5 at t2; requires confirmed prior state before t1
                         Omitting min_start is not allowed — raises ValueError to prevent silent errors.
        - years: list of int, years to apply the rule to
        """
        if len(rule) < 3:
            raise ValueError(
                f"Rule is missing min_start (3rd element): {rule}. "
                "Set min_start=0 explicitly if the rule is safe from the first year of the series."
            )

        kernel_bef = rule[0]
        kernel_aft = rule[1]
        min_start  = ee.Number(rule[2])
        years_list = ee.List(years)

        def apply_kernel_6(i, image):
            i = ee.Number(i)
            img = ee.Image(image)

            y1 = years_list.get(i)
            y2 = years_list.get(i.add(1))
            y3 = years_list.get(i.add(2))
            y4 = years_list.get(i.add(3))
            y5 = years_list.get(i.add(4))
            y6 = years_list.get(i.add(5))

            b1 = ee.String('classification_').cat(ee.String(y1))
            b2 = ee.String('classification_').cat(ee.String(y2))
            b3 = ee.String('classification_').cat(ee.String(y3))
            b4 = ee.String('classification_').cat(ee.String(y4))
            b5 = ee.String('classification_').cat(ee.String(y5))
            b6 = ee.String('classification_').cat(ee.String(y6))

            t1 = img.select(b1)
            t2 = img.select(b2)
            t3 = img.select(b3)
            t4 = img.select(b4)
            t5 = img.select(b5)
            t6 = img.select(b6)

            mask = (
                t1.eq(kernel_bef[0])
                .And(t2.eq(kernel_bef[1]))
                .And(t3.eq(kernel_bef[2]))
                .And(t4.eq(kernel_bef[3]))
                .And(t5.eq(kernel_bef[4]))
                .And(t6.eq(kernel_bef[5]))
                .And(i.gte(min_start))  # blocks windows before min index
            )

            t1 = t1.where(mask, kernel_aft[0]).rename(b1)
            t2 = t2.where(mask, kernel_aft[1]).rename(b2)
            t3 = t3.where(mask, kernel_aft[2]).rename(b3)
            t4 = t4.where(mask, kernel_aft[3]).rename(b4)
            t5 = t5.where(mask, kernel_aft[4]).rename(b5)
            t6 = t6.where(mask, kernel_aft[5]).rename(b6)

            return img.addBands([t1, t2, t3, t4, t5, t6], overwrite=True)

        # Iterate over all valid 6-year windows
        self.image = ee.List.sequence(0, len(years) - 6).iterate(apply_kernel_6, self.image)


    def apply_rule_kernel_3(self, rule, years):
        """
        Apply a 3-year kernel rule to the classification image using map().

        Parameters:
        - rule: list of three elements [kernel_bef, kernel_aft, min_start]
            - kernel_bef: list of 3 class IDs that must match the input (before state)
            - kernel_aft: list of 3 class IDs to write on match (after state)
            - min_start: int, minimum index in years from which the rule may be applied.
                         Must be set explicitly for every rule:
                         - 0: rule is safe from the first year of the series (no class 3 or 5 written at t2)
                         - 1: rule assigns class 3 or 5 at t2; requires confirmed prior state before t1
                         Omitting min_start is not allowed — raises ValueError to prevent silent errors.
        - years: list of int, years to apply the rule to
        """
        if len(rule) < 3:
            raise ValueError(
                f"Rule is missing min_start (3rd element): {rule}. "
                "Set min_start=0 explicitly if the rule is safe from the first year of the series."
            )

        kernel_bef = rule[0]
        kernel_aft = rule[1]
        min_start  = ee.Number(rule[2])
        years_list = ee.List(years)

        def apply_kernel_3(i, image):
            i = ee.Number(i)
            img = ee.Image(image)

            y1 = years_list.get(i)
            y2 = years_list.get(i.add(1))
            y3 = years_list.get(i.add(2))

            b1 = ee.String('classification_').cat(ee.String(y1))
            b2 = ee.String('classification_').cat(ee.String(y2))
            b3 = ee.String('classification_').cat(ee.String(y3))

            t1 = img.select(b1)
            t2 = img.select(b2)
            t3 = img.select(b3)

            mask = (
                t1.eq(kernel_bef[0])
                .And(t2.eq(kernel_bef[1]))
                .And(t3.eq(kernel_bef[2]))
                .And(i.gte(min_start))  # blocks windows before min index
            )

            t1 = t1.where(mask, kernel_aft[0]).rename(b1)
            t2 = t2.where(mask, kernel_aft[1]).rename(b2)
            t3 = t3.where(mask, kernel_aft[2]).rename(b3)

            return img.addBands([t1, t2, t3], overwrite=True)

        self.image = ee.List.sequence(0, len(years) - 3).iterate(apply_kernel_3, self.image)


    def apply_rules(self, rules, kernel_size, years_override=None):
        """
        Apply a list of rules using a specific kernel size.

        Parameters:
        - rules: list of rules (each rule is a pair of kernel_bef and kernel_aft)
        - kernel_size: int, must be 3, 4 or 6
        - years_override: list of int, optional, if provided overrides the default years
        """
        years = years_override or self.years
        for rule in rules:
            if kernel_size == 4:
                self.apply_rule_kernel_4(rule, years)
            elif kernel_size == 3:
                self.apply_rule_kernel_3(rule, years)
            elif kernel_size == 6:
                self.apply_rule_kernel_6(rule, years)
            else:
                raise ValueError("Kernel size must be 3, 4 or 6")

    def get_image(self):
        """
        Return the processed image after applying rules.

        Returns:
        - ee.Image: The classification image with updates from the applied rules.
        """
        return self.image

    @staticmethod
    def aggregate_classes(image, lookup_in, lookup_out):
        """
        Remap class IDs in each band from input to output values.

        Parameters:
        - image: ee.Image with classification bands
        - lookup_in: list of int, original class IDs
        - lookup_out: list of int, remapped class IDs

        Returns:
        - ee.Image with remapped bands.
        """
        band_names = image.bandNames()
        remapped = band_names.iterate(
            lambda b, acc: ee.Image(acc).addBands(
                image.select([b]).remap(lookup_in, lookup_out, 0).rename([b])
            ),
            ee.Image().select()
        )
        return ee.Image(remapped)

    @staticmethod
    def get_class_frequency(image, class_id):
        """
        Calculates per-pixel frequency of a specific class over the years.

        Parameters:
        - image: ee.Image with classification bands
        - class_id: int, class ID to count frequency for

        Returns:
        - ee.Image with frequency count per year band
        """
        bands = image.bandNames()
        base = image.select([bands.get(0)]).eq(class_id)

        def accumulate(band, acc):
            """
            Accumulate frequency for a specific class across years.

            Parameters:
            - band: string, current band name
            - acc: ee.Image, accumulated result up to this band

            Returns:
            - ee.Image with one more band added with cumulative frequency
            """
            mask = image.select([band]).eq(class_id)
            prev = ee.Image(acc).select([ee.Image(acc).bandNames().get(-1)])
            current = prev.add(mask).rename([band])
            return ee.Image(acc).addBands(current)

        return ee.Image(bands.slice(1).iterate(accumulate, base))