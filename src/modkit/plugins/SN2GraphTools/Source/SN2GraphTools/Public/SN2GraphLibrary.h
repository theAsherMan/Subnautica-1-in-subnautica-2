// Editor-only Blueprint graph building API for Python (unreal.SN2GraphLibrary).
// Pins are addressed by their internal PinName (use DescribePins to discover them).
#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "SN2GraphLibrary.generated.h"

class UBlueprint;
class UEdGraph;
class UEdGraphNode;

UCLASS()
class SN2GRAPHTOOLS_API USN2GraphLibrary : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:
	/** The Blueprint's main event graph (created if missing). */
	UFUNCTION(BlueprintCallable, Category = "SN2|Graph")
	static UEdGraph* GetEventGraph(UBlueprint* Blueprint);

	/** Removes every node from the graph. Returns the number removed. */
	UFUNCTION(BlueprintCallable, Category = "SN2|Graph")
	static int32 ClearGraph(UEdGraph* Graph);

	/** Override of a parent-class event, e.g. ReceiveBeginPlay, ReceiveTick. */
	UFUNCTION(BlueprintCallable, Category = "SN2|Graph")
	static UEdGraphNode* AddEventOverride(UBlueprint* Blueprint, UEdGraph* Graph, FName EventName, int32 X, int32 Y);

	/** New custom event. Its delegate output pin is "OutputDelegate". */
	UFUNCTION(BlueprintCallable, Category = "SN2|Graph")
	static UEdGraphNode* AddCustomEvent(UEdGraph* Graph, FName EventName, int32 X, int32 Y);

	/** Call to a UFUNCTION on FunctionOwner (static library function or member; unconnected self target = this actor). */
	UFUNCTION(BlueprintCallable, Category = "SN2|Graph")
	static UEdGraphNode* AddCallFunction(UEdGraph* Graph, UClass* FunctionOwner, FName FunctionName, int32 X, int32 Y);

	/** Instance of a StandardMacros macro (ForEachLoop, ForEachLoopWithBreak, ForLoop, WhileLoop, DoOnce, ...). */
	UFUNCTION(BlueprintCallable, Category = "SN2|Graph")
	static UEdGraphNode* AddStandardMacro(UEdGraph* Graph, FName MacroName, int32 X, int32 Y);

	/** Branch node: pins execute, Condition, then, else. */
	UFUNCTION(BlueprintCallable, Category = "SN2|Graph")
	static UEdGraphNode* AddBranch(UEdGraph* Graph, int32 X, int32 Y);

	/** Sequence node with NumOutputs outputs: then_0 .. then_N-1. */
	UFUNCTION(BlueprintCallable, Category = "SN2|Graph")
	static UEdGraphNode* AddSequence(UEdGraph* Graph, int32 NumOutputs, int32 X, int32 Y);

	/** Self reference node (pin "self"). */
	UFUNCTION(BlueprintCallable, Category = "SN2|Graph")
	static UEdGraphNode* AddSelf(UEdGraph* Graph, int32 X, int32 Y);

	/**
	 * Member variable. PinCategory e.g. "bool", "int", "real" (SubCategory "double"), "string", "name", "struct" (SubCategoryObject = struct),
	 * "object"/"class" (SubCategoryObject = class). DefaultValue uses pin default syntax ("1.5", "X=1,Y=2,Z=3", "true").
	 */
	UFUNCTION(BlueprintCallable, Category = "SN2|Graph")
	static bool AddMemberVariable(UBlueprint* Blueprint, FName Name, FName PinCategory, FName PinSubCategory, UObject* SubCategoryObject, bool bIsArray, const FString& DefaultValue);

	/** Getter (bSetter=false) or setter node for a member variable of this Blueprint. */
	UFUNCTION(BlueprintCallable, Category = "SN2|Graph")
	static UEdGraphNode* AddVariableNode(UBlueprint* Blueprint, UEdGraph* Graph, FName Name, bool bSetter, int32 X, int32 Y);

	UFUNCTION(BlueprintCallable, Category = "SN2|Graph")
	static bool SetPinDefault(UEdGraphNode* Node, const FString& PinName, const FString& Value);

	UFUNCTION(BlueprintCallable, Category = "SN2|Graph")
	static bool SetPinDefaultObject(UEdGraphNode* Node, const FString& PinName, UObject* Object);

	/** Connects From.FromPin to To.ToPin using the K2 schema rules. OutMessage explains a refusal. */
	UFUNCTION(BlueprintCallable, Category = "SN2|Graph")
	static bool Connect(UEdGraphNode* From, const FString& FromPin, UEdGraphNode* To, const FString& ToPin, FString& OutMessage);

	/** "dir name : category/subcategory(object) [default]" for every pin. */
	UFUNCTION(BlueprintCallable, Category = "SN2|Graph")
	static TArray<FString> DescribePins(UEdGraphNode* Node);

	/** Marks the Blueprint structurally modified, compiles it, returns false on error; all compiler messages in OutMessages. */
	UFUNCTION(BlueprintCallable, Category = "SN2|Graph")
	static bool CompileWithLog(UBlueprint* Blueprint, TArray<FString>& OutMessages);

	/** One line per element of an array-of-object-pointers property: "<index> <path name> outer=<outer path name>"; single line "MISSING <name>" if absent / wrong type. */
	UFUNCTION(BlueprintCallable, Category = "SN2|Reflection")
	static TArray<FString> DescribeObjectArray(UObject* Object, FName PropertyName);

	/** Empties an array-of-object-pointers property (Modify() first). Returns the removed count, -1 if the property is missing / wrong type. */
	UFUNCTION(BlueprintCallable, Category = "SN2|Reflection")
	static int32 ClearObjectArray(UObject* Object, FName PropertyName);

	/** PreEditChange + PostEditChangeProperty(ValueSet) for the named property, so the object reacts as if edited in the details panel. */
	UFUNCTION(BlueprintCallable, Category = "SN2|Reflection")
	static void NotifyPropertyChanged(UObject* Object, FName PropertyName);
};
