import xml.etree.ElementTree as ET
import json
import os
from deepdiff import DeepDiff
import shutil

# Define input and output directories
input_dir = "input"  # <--- Изменено здесь
output_dir = "out"


def parse_xml(xml_file_path):
    """
    извлекает информацию об атрибутах из XML-файла
    Args:
        xml_file_path (str): Path to the XML file.

    Returns:
        dict: A dictionary containing class information and relationships.
    """
    try:
        tree = ET.parse(xml_file_path) #ET.parse() открывает файл по указанному пути и создает объект tree, представляющий структуру XML
        root = tree.getroot() #Получает корневой элемент XML-документа. root – это объект Element, представляющий корневой тег (<XMI>)
        classes = {} #для хранения информации о классах, найденных в XML. Ключи - имена классов, значения – словари с информацией о каждом классе (документация, атрибуты).
        aggregations = [] #для хранения информации о связях агрегации между классами (например, “класс A содержит класс B”)

        for class_element in root.findall(".//Class"):
            class_name = class_element.get("name")
            classes[class_name] = {
                "documentation": class_element.get("documentation", ""),
                "attributes": {},
                "isRoot": class_element.get("isRoot") == "true",
                "min": None,
                "max": None
            }
            for attribute_element in class_element.findall(".//Attribute"): #перебор атрибутов в классе
                attribute_name = attribute_element.get("name")
                attribute_type = attribute_element.get("type")
                classes[class_name]["attributes"][attribute_name] = attribute_type

        for agg_element in root.findall(".//Aggregation"): 
            source = agg_element.get("source")
            target = agg_element.get("target")
            source_multiplicity = agg_element.get("sourceMultiplicity")
            target_multiplicity = agg_element.get("targetMultiplicity")
            aggregations.append((source, target, source_multiplicity, target_multiplicity)) #добавляет кортеж(связь агрегации между классами) в список

        return classes, aggregations
    
    except FileNotFoundError:
        print(f"Error: XML file not found at {xml_file_path}")
        return {}, []
    except ET.ParseError:
        print(f"Error: Could not parse XML file at {xml_file_path}")
        return {}, []

def generate_config_xml(classes, aggregations, output_file="config.xml"):
    """
    использует информацию об атрибутах, чтобы создать пример конфигурационного XML-файла 
        classes: Словарь, содержащий информацию о классах (имя, атрибуты, документация, isRoot, min, max), полученный из parse_xml
        aggregations: Список кортежей, содержащих информацию об агрегациях (связях) между классами, полученный из parse_xml.
    """
    try:
        root = ET.Element("BTSConfig") #Создает корневой элемент XML-документа с именем «BTSConfig»

        bts_element = ET.SubElement(root, "BTS") #Создает подэлемент «BTS» внутри корневого элемента «BTSConfig», который будет содержать конфигурацию для самой базовой станции

        if "BTS" in classes:
            for attribute_name, attribute_type in classes["BTS"]["attributes"].items():
                attribute_element = ET.SubElement(bts_element, attribute_name)
                if attribute_type == "uint32":
                    attribute_element.text = "0"
                elif attribute_type == "string":
                    attribute_element.text = ""
                elif attribute_type == "boolean":
                    attribute_element.text = "false"

        for source, target, *_ in aggregations: 
            if source == "MGMT" and target == "BTS":
                mgmt_element = ET.SubElement(bts_element, "MGMT")
                if "MGMT" in classes:
                    if "MetricJob" in classes:
                        metric_job_element = ET.SubElement(mgmt_element, "MetricJob")
                        for attr_name, attr_type in classes["MetricJob"]["attributes"].items():
                            attr_element = ET.SubElement(metric_job_element, attr_name)
                            if attr_type == "boolean":
                                attr_element.text = "false"
                            elif attr_type == "uint32":
                                attr_element.text = "0"
                    if "CPLANE" in classes:
                        cplane_element = ET.SubElement(mgmt_element, "CPLANE")
            elif source == "HWE" and target == "BTS":
                hwe_element = ET.SubElement(bts_element, "HWE")
                if "HWE" in classes:
                    if "RU" in classes:
                        ru_element = ET.SubElement(hwe_element, "RU")
                        for attr_name, attr_type in classes["RU"]["attributes"].items():
                            attr_element = ET.SubElement(ru_element, attr_name)
                            if attr_type == "string":
                                attr_element.text = ""
                            elif attr_type == "uint32":
                                attr_element.text = "0"

            elif source == "COMM" and target == "BTS":
                comm_element = ET.SubElement(bts_element, "COMM")

        tree = ET.ElementTree(root)
        output_path = os.path.join(output_dir, output_file)  
        tree.write(output_path, encoding="utf-8", xml_declaration=True)
    except Exception as e:
        print(f"Error generating config.xml: {e}")


def generate_meta_json(classes, aggregations, output_file="meta.json"):

    try:
        meta_data = []

        for class_name, class_data in classes.items():
            class_meta = {
                "class": class_name,
                "documentation": class_data["documentation"],
                "isRoot": class_data["isRoot"],
                "parameters": []
            }

            for attr_name, attr_type in class_data["attributes"].items():
                class_meta["parameters"].append({
                    "name": attr_name,
                    "type": attr_type
                })

            for source, target, source_multiplicity, target_multiplicity in aggregations:
                if target == class_name and source in classes:
                    class_meta["parameters"].append({
                        "name": source,
                        "type": "class"
                    })

            meta_data.append(class_meta)
        output_path = os.path.join(output_dir, output_file)  
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(meta_data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"Error generating meta.json: {e}")

def calculate_delta(config_json_file_path, patched_config_json_file_path, output_file="delta.json"):
    try:
        with open(config_json_file_path, "r") as f:
            config_data = json.load(f)
    except FileNotFoundError:
        print(f"Error: config.json not found at {config_json_file_path}")
        return {}
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON format in config.json at {config_json_file_path}")
        return {}

    try:
        with open(patched_config_json_file_path, "r") as f:
            patched_config_data = json.load(f)
    except FileNotFoundError:
        print(f"Error: patched_config.json not found at {patched_config_json_file_path}")
        return {}
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON format in patched_config.json at {patched_config_json_file_path}")
        return {}

    diff = DeepDiff(config_data, patched_config_data, ignore_order=True)

    delta = {
        "additions": {},
        "deletions": {},
        "updates": {}
    }

    if "dictionary_item_added" in diff:
        for item in diff["dictionary_item_added"]:
            parts = item.split("'")
            if len(parts) > 1:
                key_path = parts[1]
                value = patched_config_data
                for key in key_path.split('.'):
                    if isinstance(value, dict) and key in value:
                        value = value[key]
                    else:
                        value = None
                        break
                if value is not None:
                    delta["additions"][key_path] = value

    if "dictionary_item_removed" in diff:
        for item in diff["dictionary_item_removed"]:
            parts = item.split("'")
            if len(parts) > 1:
                key_path = parts[1]
                value = config_data
                for key in key_path.split('.'):
                    if isinstance(value, dict) and key in value:
                        value = value[key]
                    else:
                        value = None
                        break
                if value is not None:
                    delta["deletions"][key_path] = value

    if "values_changed" in diff:
        for item, changes in diff["values_changed"].items():
            parts = item.split("'")
            if len(parts) > 1:
                key_path = parts[1]
                delta["updates"][key_path] = {
                    "old_value": changes["old_value"],
                    "new_value": changes["new_value"]
                }

    output_path = os.path.join(output_dir, output_file)
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(delta, f, indent=4)
    except Exception as e:
        print(f"Error writing delta.json: {e}")

    return delta

def apply_delta(config_json_file_path, delta, output_file="res_patched_config.json"):
    try:
        with open(config_json_file_path, "r") as f:
            config_data = json.load(f)
    except FileNotFoundError:
        print(f"Error: config.json not found at {config_json_file_path}")
        return
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON format in config.json at {config_json_file_path}")
        return

    for key_path, value in delta.get("additions", {}).items():
        keys = key_path.split(".")
        current_level = config_data
        for i, key in enumerate(keys[:-1]):
            if key not in current_level:
                current_level[key] = {}
            current_level = current_level[key]
        current_level[keys[-1]] = value

    for key_path in delta.get("deletions", {}).keys():
        keys = key_path.split(".")
        current_level = config_data
        for i, key in enumerate(keys[:-1]):
            if key in current_level:
                current_level = current_level[key]
            else:
                break  # If the key does not exist, there is nothing to delete
        if keys[-1] in current_level:
            del current_level[keys[-1]]
        # Consider recursive deletion of empty parent objects

    for key_path, update in delta.get("updates", {}).items():
        keys = key_path.split(".")
        current_level = config_data
        for i, key in enumerate(keys[:-1]):
            if key not in current_level:
                current_level[key] = {}  # Create missing dictionaries along the path
            current_level = current_level[key]
        current_level[keys[-1]] = update["new_value"]

    output_path = os.path.join(output_dir, output_file)
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=4)
    except Exception as e:
        print(f"Error writing res_patched_config.json: {e}")

def main():
    # 1. Parse XML
    xml_file_path = os.path.join(input_dir, "impulse_test_input.xml")
    classes, aggregations = parse_xml(xml_file_path)

    # 2. Generate config.xml
    generate_config_xml(classes, aggregations)

    # 3. Generate meta.json
    generate_meta_json(classes, aggregations)

    # 4. Calculate and save delta.json
    config_json_path = os.path.join(input_dir, "config.json")
    patched_config_json_path = os.path.join(input_dir, "patched_config.json")
    delta = calculate_delta(config_json_path, patched_config_json_path)

    # 5. Apply delta and save res_patched_config.json
    apply_delta(config_json_path, delta)

    print("Artifacts generated successfully.")

if __name__ == "__main__":
    main()