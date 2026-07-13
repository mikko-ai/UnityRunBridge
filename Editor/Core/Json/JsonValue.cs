using System;
using System.Collections.Generic;
using System.Globalization;

namespace Mk.UnityAgentBridge.Editor.Json
{
    public enum JsonValueType
    {
        Null,
        Boolean,
        Number,
        String,
        Array,
        Object
    }

    /// <summary>
    /// 自写的最小 JSON 值模型：带类型标签的树形结构（object/array/string/number/bool/null）。
    /// API 造型参照 Newtonsoft JObject/JToken 的常用面（字符串索引器、TryGet、类型转换访问器），
    /// 实现完全自研，不依赖也不拷贝 Newtonsoft 代码。仅供 Editor 代码使用。
    ///
    /// object 属性顺序按插入顺序保留（不用 Dictionary 的隐式顺序），
    /// 保证同一份数据序列化结果是确定性的，便于测试断言与调试。
    /// </summary>
    public sealed class JsonValue
    {
        private enum NumberKind
        {
            Integer,
            Float
        }

        public JsonValueType Type { get; }

        private readonly bool boolValue;
        private readonly long integerValue;
        private readonly double floatValue;
        private readonly NumberKind numberKind;
        private readonly string stringValue;
        private readonly List<JsonValue> arrayItems;
        private readonly List<string> objectKeyOrder;
        private readonly Dictionary<string, JsonValue> objectItems;

        public static readonly JsonValue Null = new JsonValue(JsonValueType.Null);
        public static readonly JsonValue True = new JsonValue(true);
        public static readonly JsonValue False = new JsonValue(false);

        private JsonValue(JsonValueType type)
        {
            Type = type;
        }

        private JsonValue(bool value)
        {
            Type = JsonValueType.Boolean;
            boolValue = value;
        }

        private JsonValue(long value)
        {
            Type = JsonValueType.Number;
            numberKind = NumberKind.Integer;
            integerValue = value;
            floatValue = value;
        }

        private JsonValue(double value)
        {
            if (double.IsNaN(value) || double.IsInfinity(value))
            {
                throw new JsonWriterException("NaN/Infinity 不是合法 JSON 数值，无法构造 JsonValue");
            }

            Type = JsonValueType.Number;
            numberKind = NumberKind.Float;
            floatValue = value;
        }

        private JsonValue(string value)
        {
            Type = JsonValueType.String;
            stringValue = value ?? string.Empty;
        }

        private JsonValue(List<JsonValue> items)
        {
            Type = JsonValueType.Array;
            arrayItems = items;
        }

        private JsonValue(List<string> keyOrder, Dictionary<string, JsonValue> items)
        {
            Type = JsonValueType.Object;
            objectKeyOrder = keyOrder;
            objectItems = items;
        }

        public static JsonValue FromBoolean(bool value) => value ? True : False;
        public static JsonValue FromInteger(long value) => new JsonValue(value);
        public static JsonValue FromInteger(int value) => new JsonValue((long)value);
        public static JsonValue FromDouble(double value) => new JsonValue(value);
        public static JsonValue FromString(string value) => value == null ? Null : new JsonValue(value);
        public static JsonValue NewArray() => new JsonValue(new List<JsonValue>());
        public static JsonValue NewObject() => new JsonValue(new List<string>(), new Dictionary<string, JsonValue>(StringComparer.Ordinal));

        public static implicit operator JsonValue(bool value) => FromBoolean(value);
        public static implicit operator JsonValue(int value) => FromInteger(value);
        public static implicit operator JsonValue(long value) => FromInteger(value);
        public static implicit operator JsonValue(double value) => FromDouble(value);
        public static implicit operator JsonValue(float value) => FromDouble(value);
        public static implicit operator JsonValue(string value) => FromString(value);

        public bool IsNull => Type == JsonValueType.Null;
        public bool IsBoolean => Type == JsonValueType.Boolean;
        public bool IsNumber => Type == JsonValueType.Number;
        public bool IsString => Type == JsonValueType.String;
        public bool IsArray => Type == JsonValueType.Array;
        public bool IsObject => Type == JsonValueType.Object;
        internal bool IsIntegerNumber => IsNumber && numberKind == NumberKind.Integer;

        public bool AsBoolean
        {
            get
            {
                RequireType(JsonValueType.Boolean);
                return boolValue;
            }
        }

        public long AsLong
        {
            get
            {
                RequireType(JsonValueType.Number);
                return numberKind == NumberKind.Integer ? integerValue : (long)floatValue;
            }
        }

        public int AsInt => (int)AsLong;

        public double AsDouble
        {
            get
            {
                RequireType(JsonValueType.Number);
                return numberKind == NumberKind.Integer ? integerValue : floatValue;
            }
        }

        public float AsFloat => (float)AsDouble;

        public string AsString
        {
            get
            {
                RequireType(JsonValueType.String);
                return stringValue;
            }
        }

        public List<JsonValue> Items
        {
            get
            {
                RequireType(JsonValueType.Array);
                return arrayItems;
            }
        }

        public int Count
        {
            get
            {
                if (Type == JsonValueType.Array)
                {
                    return arrayItems.Count;
                }

                if (Type == JsonValueType.Object)
                {
                    return objectKeyOrder.Count;
                }

                throw new InvalidOperationException($"JsonValue of type {Type} has no Count");
            }
        }

        public IEnumerable<string> Keys
        {
            get
            {
                RequireType(JsonValueType.Object);
                return objectKeyOrder;
            }
        }

        public IEnumerable<KeyValuePair<string, JsonValue>> Properties
        {
            get
            {
                RequireType(JsonValueType.Object);
                foreach (string key in objectKeyOrder)
                {
                    yield return new KeyValuePair<string, JsonValue>(key, objectItems[key]);
                }
            }
        }

        /// <summary>
        /// 对象索引器：get 时缺失键返回 <see cref="Null"/>（而不是抛异常），
        /// 与常见 JSON 库的宽松取值习惯一致；set 时保持插入顺序（覆盖已存在键不改变其原有位置）。
        /// </summary>
        public JsonValue this[string key]
        {
            get
            {
                RequireType(JsonValueType.Object);
                return objectItems.TryGetValue(key, out JsonValue value) ? value : Null;
            }
            set
            {
                RequireType(JsonValueType.Object);
                if (!objectItems.ContainsKey(key))
                {
                    objectKeyOrder.Add(key);
                }

                objectItems[key] = value ?? Null;
            }
        }

        public JsonValue this[int index]
        {
            get
            {
                RequireType(JsonValueType.Array);
                if (index < 0 || index >= arrayItems.Count)
                {
                    throw new ArgumentOutOfRangeException(nameof(index));
                }

                return arrayItems[index];
            }
            set
            {
                RequireType(JsonValueType.Array);
                if (index < 0 || index >= arrayItems.Count)
                {
                    throw new ArgumentOutOfRangeException(nameof(index));
                }

                arrayItems[index] = value ?? Null;
            }
        }

        public void Add(JsonValue item)
        {
            RequireType(JsonValueType.Array);
            arrayItems.Add(item ?? Null);
        }

        public void Set(string key, JsonValue value)
        {
            this[key] = value;
        }

        public bool ContainsKey(string key)
        {
            return Type == JsonValueType.Object && objectItems.ContainsKey(key);
        }

        public bool TryGet(string key, out JsonValue value)
        {
            if (Type == JsonValueType.Object && objectItems.TryGetValue(key, out value))
            {
                return true;
            }

            value = null;
            return false;
        }

        public bool TryGetString(string key, out string value)
        {
            if (TryGet(key, out JsonValue item) && item.IsString)
            {
                value = item.AsString;
                return true;
            }

            value = null;
            return false;
        }

        public bool TryGetLong(string key, out long value)
        {
            if (TryGet(key, out JsonValue item) && item.IsNumber)
            {
                value = item.AsLong;
                return true;
            }

            value = 0;
            return false;
        }

        public bool TryGetDouble(string key, out double value)
        {
            if (TryGet(key, out JsonValue item) && item.IsNumber)
            {
                value = item.AsDouble;
                return true;
            }

            value = 0;
            return false;
        }

        public bool TryGetBoolean(string key, out bool value)
        {
            if (TryGet(key, out JsonValue item) && item.IsBoolean)
            {
                value = item.AsBoolean;
                return true;
            }

            value = false;
            return false;
        }

        public bool TryGetObject(string key, out JsonValue value)
        {
            if (TryGet(key, out JsonValue item) && item.IsObject)
            {
                value = item;
                return true;
            }

            value = null;
            return false;
        }

        public bool TryGetArray(string key, out JsonValue value)
        {
            if (TryGet(key, out JsonValue item) && item.IsArray)
            {
                value = item;
                return true;
            }

            value = null;
            return false;
        }

        public string GetString(string key, string defaultValue = null)
        {
            return TryGetString(key, out string value) ? value : defaultValue;
        }

        public long GetLong(string key, long defaultValue = 0)
        {
            return TryGetLong(key, out long value) ? value : defaultValue;
        }

        public double GetDouble(string key, double defaultValue = 0)
        {
            return TryGetDouble(key, out double value) ? value : defaultValue;
        }

        public bool GetBoolean(string key, bool defaultValue = false)
        {
            return TryGetBoolean(key, out bool value) ? value : defaultValue;
        }

        private void RequireType(JsonValueType expected)
        {
            if (Type != expected)
            {
                throw new InvalidOperationException($"JsonValue is {Type}, expected {expected}");
            }
        }

        public override string ToString()
        {
            return JsonWriter.Serialize(this);
        }
    }

    public sealed class JsonWriterException : Exception
    {
        public JsonWriterException(string message) : base(message)
        {
        }
    }

    public sealed class JsonParseException : Exception
    {
        public int Position { get; }

        public JsonParseException(string message, int position)
            : base($"{message} (at char {position})")
        {
            Position = position;
        }
    }
}
